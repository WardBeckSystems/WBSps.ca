"""Convert every PCB in the archive to KiCad, with renders and a summary per board.

Usage: python3 convert_boards.py <source folder (read-only)> <output folder>

- Tango-PCB Plus ASCII .PCB -> tango2kicad.py, with the best-matching Tango .NET from the same project
  folder when at least 60% of its pins land on the board.
- Eagle XML .brd -> KiCad's own Eagle importer.
- Anything else (P-CAD 2002 binary, Tango binary) is listed as skipped.
Identical files (same SHA-256) are converted once; every original path is recorded.
Writes <out>/<project> - <board>/ with .kicad_pcb, -top.svg, -bottom.svg, README.md, board.json,
and <out>/boards.json + <out>/index.html.
"""
import collections, hashlib, html, json, os, re, subprocess, sys

SRC, OUT = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
TOOLS = os.path.dirname(os.path.abspath(__file__))
e = html.escape


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def fmt(p):
    with open(p, 'rb') as f:
        head = f.read(200)
    if head.startswith(b';Tango-PCB'):
        return 'tango'
    if b'<eagle' in head or (head.startswith(b'<?xml') and p.lower().endswith('.brd')):
        return 'eagle'
    if b'P-CAD' in head:
        return 'pcad-binary'
    return 'unknown'


def board_pins(p):
    pins = set()
    comps = {}
    with open(p, errors='replace') as f:
        for line in f:
            m = re.match(r'COMP "([^"]*)".* (\d+) \d+\s*$', line)
            if m:
                comps[m.group(2)] = m.group(1)
            m = re.match(r'PAD \S+ \d+ \d+ \d+ \S+ \S+ "([^"]*)" -?\d+ -?\d+ -?\d+ (\d+)', line)
            if m and m.group(2) in comps:
                pins.add((comps[m.group(2)], m.group(1)))
    return pins


def net_nodes(p):
    with open(p, errors='replace') as f:
        body = f.read().replace('\r', '')
    return [tuple(x.strip().partition(',')[::2]) for blk in re.findall(r'^\(\n(.*?)\n\)', body, re.M | re.S)
            for x in blk.split('\n')[1:] if ',' in x]


def board_parts(p):
    out = {}
    with open(p, errors='replace') as f:
        for line in f:
            m = re.match(r'COMP "([^"]*)" "[^"]*" "[^"]*" "([^"]*)"', line)
            if m:
                out[m.group(1)] = m.group(2).upper()
    return out


def net_parts(p):
    with open(p, errors='replace') as f:
        body = f.read().replace('\r', '')
    return {b.split('\n')[0].strip(): b.split('\n')[1].strip().upper()
            for b in re.findall(r'^\[\n(.*?)\n\]', body, re.M | re.S) if '\n' in b}


def best_netlist(board):
    """Look in the board's folder, its subfolders and its parent for this board's Tango netlist.
    Plain refs (R1, C1...) are on every board, so a netlist counts only when its parts agree
    with the board's on reference *and* footprint, and it covers a fair share of the board."""
    parts = board_parts(board)
    if not parts:
        return None, 0
    here = os.path.dirname(board)
    cands = set()
    for base in (here, os.path.dirname(here)):
        for r, _, fs in os.walk(base):
            if r.count(os.sep) - base.count(os.sep) > 2:
                continue
            cands.update(os.path.join(r, f) for f in fs if f.lower().endswith('.net'))
    best, score = None, 0
    for c in sorted(cands):
        nparts = net_parts(c)
        if len(nparts) < 0.4 * len(parts):
            continue
        s = sum(1 for r, fp in nparts.items() if parts.get(r) == fp) / len(nparts)
        if s >= 0.8 and s > score:
            best, score = c, s
    return best, score


sys.path.insert(0, TOOLS)
from titles import title_info, safe_filename, wordy, domain_score  # noqa: E402


def scan_titles():
    """Title-block names from the scan databases, by drawing series (14-302) and by SA14 device (SA14-288 -> 14-288)"""
    out = {}
    scans = os.path.join(os.path.dirname(OUT), 'Scans')
    for d in sorted(os.listdir(scans)) if os.path.isdir(scans) else []:
        db = os.path.join(scans, d, 'scans.db')
        if not os.path.exists(db):
            continue
        con = __import__('sqlite3').connect(f'file:{db}?mode=ro', uri=True)
        stored = 'display_name' in {r[1] for r in con.execute('pragma table_info(scans)')}
        rows = con.execute("select rel, kind, method, text, title_block" + (", dwg_no, device, title, title_source" if stored else "") +
                           " from scans where method not in ('strings', 'skipped')")
        for rel, kind, method, text, tb, *saved in rows:
            if kind == 'photo':
                continue
            # the title fields scan_ingest --retag stored (with its drawing-number repairs), else worked out here
            t = dict(zip(('dwg_no', 'device', 'title', 'title_source'), saved)) if saved else title_info(text or '', tb or '', rel, {}, kind)
            if not t['title']:
                continue
            dwg = t['dwg_no']
            series = dwg.rsplit('-', 2)[0] if dwg else ''
            guessed = bool(series and re.fullmatch(r'\d{3}', series))
            if guessed:
                series = '14-' + series  # SA14 drawings lose their 14- to OCR; a guess, so it ranks lowest
            named = re.sub(r'^SA', '', t['device'] or '')
            for key in {series, named} - {''}:
                # the board's own SA14 number in the title > a title block > text > a guessed series
                rank = 4 if key == named and named.startswith('14-') else 3 if t['title_source'] == 'title block' and not guessed else 2 if not guessed else 1
                if rank > out.get(key, (0,))[0]:
                    out[key] = (rank, t['device'], t['title'])
        con.close()
    return out


SCAN_TITLES = scan_titles()


def board_title(stem, netlist):
    """A board's name as its own documents write it: a drawing title block first, then the netlist header,
    then a manual or drawing that mentions its number."""
    hit = SCAN_TITLES.get(stem.upper())
    from_scan = ''
    if hit:
        _, device, title = hit
        from_scan = title if not device or device in title else f'{device} {title}'
        if hit[0] >= 3:  # names the board itself, or read from a title block
            return from_scan
        if not device and not domain_score(title):  # body text ("SOLID LINE", "ITEM QUANTITY ...") is no name
            from_scan = ''
    if netlist:
        with open(netlist, errors='replace') as f:
            head = [l.strip() for l in f.read(600).replace('\r', '').split('\n')[:2] if l.strip()]
        first = re.split(r'\s{3,}', head[0])[0].strip() if head else ''
        if wordy(first) and not re.search(r'REVIS|UNDEFINED|^-', first, re.I) and len(first.split()) >= 2:
            return first.upper()
    return from_scan


def slug(path, title=''):
    proj = re.sub(r'^(WBSps|Wbsps) - ', '', os.path.basename(os.path.dirname(path)))
    stem = os.path.splitext(os.path.basename(path))[0]
    plain = re.fullmatch(r'TANGO|OLD\d*|ISS\d*|ORCAD|TMP|WORK|NEW', proj, re.I)  # storage folders, not names
    name = f'{stem} - {title}' if title else stem if plain else f'{stem} - {proj}'
    return safe_filename(re.sub(r'\s+', ' ', name), 90)


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600)


EAGLE = '''import pcbnew, sys
b = pcbnew.PCB_IO_MGR.Load(pcbnew.PCB_IO_MGR.EAGLE, sys.argv[1])
pcbnew.SaveBoard(sys.argv[2], b)
print(len(b.GetFootprints()), len(b.GetTracks()))
'''

groups = collections.defaultdict(list)
for r, ds, fs in os.walk(SRC):
    ds.sort()
    for f in sorted(fs):
        if f.lower().endswith(('.pcb', '.brd')):
            p = os.path.join(r, f)
            groups[sha(p)].append(p)

os.makedirs(OUT, exist_ok=True)
boards, used = [], set()
for h, paths in sorted(groups.items(), key=lambda kv: slug(kv[1][0])):
    paths.sort(key=lambda p: ('-2026' in p, len(p)))  # prefer the main tree over the zip parts
    src = paths[0]
    kind = fmt(src)
    net, score = best_netlist(src) if kind == 'tango' else (None, 0)
    title = board_title(os.path.splitext(os.path.basename(src))[0], net)
    name = slug(src, title)
    while name in used:
        name += '+'
    used.add(name)
    d = os.path.join(OUT, name)
    rec = {'board': name, 'title': title, 'format': kind, 'sha256': h, 'source': os.path.relpath(src, SRC),
           'copies': [os.path.relpath(p, SRC) for p in paths], 'kicad_pcb': None}
    stem = os.path.splitext(os.path.basename(src))[0]
    pcb = os.path.join(d, stem + '.kicad_pcb')
    if kind == 'tango':
        cmd = ['python3', os.path.join(TOOLS, 'tango2kicad.py'), src, d] + (['--net', net] if net else [])
        res = run(cmd)
        rec['netlist'] = {'file': os.path.relpath(net, SRC), 'match': round(score, 2)} if net else None
        try:
            rec['convert'] = json.load(open(os.path.join(d, stem + '.convert.json')))
        except (OSError, ValueError):
            rec['error'] = res.stderr[-800:]
    elif kind == 'eagle':
        os.makedirs(d, exist_ok=True)
        res = run(['python3', '-c', EAGLE, src, pcb])
        if res.returncode or not os.path.exists(pcb):
            rec['skipped'] = ("Eagle import needs KiCad's layer-mapping dialog: open it in KiCad with "
                              "File > Import > Non-KiCad Board File")
    else:
        rec['skipped'] = 'P-CAD 2002 binary: KiCad imports only P-CAD ASCII' if kind == 'pcad-binary' else 'unrecognised format'
    if os.path.exists(pcb):
        rec['kicad_pcb'] = os.path.relpath(pcb, OUT)
        for side, layers, extra in (('top', 'F.Cu,F.SilkS,Edge.Cuts', []), ('bottom', 'B.Cu,B.SilkS,Edge.Cuts', ['--mirror'])):
            svg = os.path.join(d, f'{stem}-{side}.svg')
            run(['kicad-cli', 'pcb', 'export', 'svg', '--layers', layers, '--mode-single', '--page-size-mode', '2',
                 '--exclude-drawing-sheet', *extra, '-o', svg, pcb])
            if os.path.exists(svg):
                rec[side] = os.path.relpath(svg, OUT)
        c = rec.get('convert', {}).get('counts', {})
        with open(os.path.join(d, 'README.md'), 'w') as f:
            f.write(f'# {name}\n\n' + (f'**{title}**\n\n' if title else '') +
                    f'Converted to KiCad from `{rec["source"]}` ({kind}).\n\n')
            if rec.get('top'):
                f.write(f'![Top]({os.path.basename(rec["top"])})\n\n')
            if c:
                f.write('| Components | Pads | Track segments | Vias | Pours |\n|---|---|---|---|---|\n'
                        f'| {c.get("components")} | {c.get("pads")} | {c.get("tracks")} | {c.get("vias")} | {c.get("pours")} |\n\n')
            nl = rec.get('netlist')
            applied = rec.get('convert', {}).get('nets', {}) or {}
            f.write(f'Nets: {"from `" + nl["file"] + "`" if nl and applied.get("applied") else "none (no matching netlist)"}.\n\n')
            f.write('Other copies of the same file:\n\n' + ''.join(f'- `{p}`\n' for p in rec['copies'][1:]) if len(rec['copies']) > 1 else '')
        with open(os.path.join(d, 'board.json'), 'w') as f:
            json.dump(rec, f, indent=2)
    boards.append(rec)
    print(f'{kind:12} {name}', '✓' if rec['kicad_pcb'] else rec.get('skipped') or 'FAILED', flush=True)

with open(os.path.join(OUT, 'boards.json'), 'w') as f:
    json.dump(boards, f, indent=2)

from urllib.parse import quote
q = lambda p: '/'.join(quote(x) for x in p.split('/'))
cards = ''.join(
    f'<li><a href="{q(b["kicad_pcb"].rsplit("/", 1)[0])}/README.md"><img loading="lazy" src="{q(b["top"])}" alt=""></a>'
    f'<b>{e(b["board"])}</b><small>{e(b["format"])} · {b.get("convert", {}).get("counts", {}).get("components", "?")} parts'
    f'{" · nets" if (b.get("convert", {}).get("nets") or {}).get("applied") else ""}</small>'
    f'<a href="{q(b["kicad_pcb"])}">.kicad_pcb</a></li>'
    for b in boards if b.get('top'))
skipped = ''.join(f'<li>{e(b["board"])}: {e(b.get("skipped") or b.get("error", "failed")[:120])}</li>' for b in boards if not b.get('top'))
with open(os.path.join(OUT, 'index.html'), 'w') as f:
    f.write(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>WBS Boards in KiCad</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Overpass:wght@400;700;800&family=Overpass+Mono&display=swap">
<style>
/* Layout: a drawing-sheet grid of board renders. Single look by design. */
:root {{ --paper: #f7f6ef; --ink: #1c1c1c; --faint: #66635c; color-scheme: light }}
body {{ margin: 0; background: #d9d6ca; color: var(--ink); font: 14px/1.4 "Overpass", Arial, sans-serif;
  padding-block: 20px; padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)) }}
main {{ max-width: 1240px; margin: 0 auto; background: var(--paper); border: 2px solid var(--ink); padding: 22px }}
h1 {{ margin: 0 0 4px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; font-size: 22px }}
p {{ color: var(--faint); margin: 0 0 18px }}
ul.g {{ list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr)); gap: 16px }}
ul.g li {{ border: 1px solid var(--ink); background: #fff; padding: 8px; display: grid; gap: 4px }}
ul.g img {{ width: 100%; aspect-ratio: 4 / 3; object-fit: contain; background: #f2f0e6 }}
small {{ color: var(--faint); font-family: "Overpass Mono", monospace }}
a {{ color: inherit }}
h2 {{ font-size: 13px; letter-spacing: .14em; text-transform: uppercase; border-bottom: 1.5px solid var(--ink); margin-top: 28px }}
</style></head><body><main>
<h1>WBS boards in KiCad</h1>
<p>{sum(1 for b in boards if b.get("top"))} boards converted from the original Tango-PCB and Eagle files. Click a render for its notes; open the .kicad_pcb in KiCad 9.</p>
<ul class="g">{cards}</ul>
{f"<h2>Not converted</h2><ul>{skipped}</ul>" if skipped else ""}
</main></body></html>''')
print(f'{sum(1 for b in boards if b["kicad_pcb"])} of {len(boards)} boards converted to {OUT}')
