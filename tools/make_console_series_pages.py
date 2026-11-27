#!/usr/bin/env python3
"""Console series pages: PAGES/Series-<name>.md and .html for each console series (Renaissance, R2K, R2K Cool Grey).

    python3 tools/make_console_series_pages.py

Each page: what the series is (read from its manuals), the dated evidence, the marks or sizes, the modules (linked to
their wiki pages), the specifications, and every manual, drawing and photo of the series (Google Drive links, the
note of each file). Files come from 2026/Consoles/Models/<folder>; a series takes the files SERIES[...]['take'] picks.
The consoles index (PAGES/Consoles.md/.html) gets a "Console series" section, the project pages a link.
Web thumbnails (<name>_small.jpg beside <name>.jpg) are left out.
"""
import glob
import html as H
import json
import os
import re
from urllib.parse import quote

import markdown

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Y = os.path.join(ROOT, '2026')
PAGES = os.path.join(ROOT, 'PAGES')
RS = 'Consoles/Models/R series (Renaissance)'
FOOT = 'Archive: Anthony Peter Kuzub · [WBSps.ca](https://WBSps.ca) · [WBSps.Kuzub.com](https://WBSps.Kuzub.com)'
SHOWN = ('.pdf', '.jpg', '.jpeg', '.png', '.gif', '.tif', '.tiff', '.docx', '.doc', '.wpg')
PHOTO_DIRS = ('Renaisance Console', 'WBS renaisance console')

# The modules each Cool Grey manual section names (Cool Grey Manual, Input Modules Manual); the rest of R2K/ is the R2K.
COOL = re.compile(r'Cool Grey|INPUT MODULES MANUAL|\bR2(?:4\d|50|58|59)\b', re.I)


def yt(y):
    return f'{y}|{int(y) - 1967}'


def ylink(y):
    return f'[{yt(y).replace("|", "\\|")}](Year-{y}.md)'


SERIES = {
    'Renaissance': dict(
        title='Renaissance — Stereo Radio Audio Console',
        dirs=['Renaisance', 'Renaisance Console', 'WBS renaisance console'],
        take=lambda rel: True,
        next='R2K',
        about=[
            'The Renaissance is Ward-Beck Systems\' standard stereo radio audio console of the 1990s, built from the M900 '
            'series of modules in a desk-top frame with a meter bridge. It came in three standard sizes, MKI, MKII and '
            'MKIII, each with its own control panel (CPMK I, II, III); each standard console shipped with a test '
            'result, a module list, the product manuals of its modules and its system drawings.',
            'Its mixing buses (from the console summing-bus drawing): MUSIC and VOICE program, MIX, CUE, AUX, '
            'with inserts and metering. Custom consoles were drawn from it under job numbers 940238 and 940444 (1994).',
            'It was followed by the [R2K](Series-R2K.md) (the "Renaissance R2K Audio Console") and the '
            '[R2K Cool Grey](Series-R2K-Cool-Grey.md). The earlier R series of 1990 (R1400, R2200, R2400) is on the '
            '[R1400](R1400.md) page.',
        ],
        evidence=[
            (1994, 'drawing numbers 940238-02-070, 940238-02-080, 940444-02-100, 940444-02-200: the Renaissance module '
                   'schematics (job numbers, first two digits the year)'),
            (1997, 'MKI, MKII and MKIII manuals: every system drawing (MKIL03 … MKIIIL33) issue 1/97'),
            (2010, 'screen shots of the Renaissance console, 2010-03-25'),
        ],
        marks=('Size', [
            ('MKI', '25.75 in (654 mm)', '24-5/8 in', 'CPMK I'),
            ('MKII', '37.75 in (959 mm)', '36-5/8 in', 'CPMK II'),
            ('MKIII', '49.75 in (1264 mm)', '48-5/8 in', 'CPMK III'),
        ], 'All three: 7.50 in (190 mm) above the desk, 17.20 in (437 mm) total height, 24.85 in (631 mm) deep; '
           'desk cutout 22-3/16 in deep (tolerance −0.0 / +1/16 in).'),
        modules=[
            ('M901A', 'Input Module'), ('M901B', 'Mic Input Module'), ('M901C', 'Stereo Line Input Module'),
            ('M901D', 'Stereo Input Module'), ('M901E', 'Stereo Input Module'),
            ('M905A', 'Control Room Monitor Module'), ('M905B', 'Studio Monitor Module'),
            ('M907', 'Summing / Program Output Amplifier Module'), ('M908', 'Dual 10×1 Stereo Selector Module'),
            ('M909', 'Meter Mix / Minus Module'), ('M922', 'Stereo Equalizer Module'), ('M922A', 'Mono Equalizer Module'),
            ('M924B', 'Power Supply'), ('TMR-IR', 'Timer'), ('CLK-IR', 'Clock'),
            ('CPMK', 'Control Panel (CPMK I / II / III)'),
        ],
        modules_from='the "List of separately supplied standard product manuals" in the MKI and MKIII manuals',
        specs=[
            ('Mic inputs', '150 Ω source; input impedance greater than 1500 Ω balanced; sensitivity −60 to −30 dBm, '
                           'continuously variable; 23 dB headroom'),
            ('Line inputs', '600 Ω or less source; input impedance greater than 20 kΩ balanced; sensitivity −10 to '
                            '+10 dBu, continuously variable; 23 dB headroom'),
            ('Program outputs', '60 Ω balanced, into 600 Ω or greater; +4 dBu nominal, +27 dBm maximum'),
            ('Monitor outputs', '60 Ω balanced, into 600 Ω or greater; +20 dBu maximum'),
            ('Frequency response', '±0.25 dB 30 Hz – 15 kHz; ±0.5 dB 20 Hz – 20 kHz'),
            ('Distortion (THD)', 'line channels less than 0.07 %, mic channels less than 0.2 %, 20 Hz – 20 kHz at +14 dBu'),
            ('Noise', 'mic EIN lower than −125 dBm; high level S/N greater than 85 dB below +14 dBu, 20 Hz – 20 kHz'),
            ('Crosstalk / separation', 'greater than 75 dB / left-right greater than 60 dB'),
            ('Power', '85–264 V ac, 47–63 Hz'),
        ],
        specs_from='"Renaissance Stereo Radio Consoles — Technical Specifications", MKI manual pp. 59–60',
    ),
    'R2K': dict(
        title='R2K — Renaissance R2K Audio Console',
        dirs=['R2K'],
        take=lambda rel: not COOL.search(os.path.basename(rel)),
        prev='Renaissance', next='R2K-Cool-Grey',
        about=[
            'The R2K ("Renaissance R2K Audio Console") is the successor of the [Renaissance](Series-Renaissance.md): '
            'a stereo radio console of R200 modules, drawn from 1998 to 2000. Its technical instruction manual has '
            'one section per module, then the console diagrams, the guest turret and the Torpey clock '
            '(the remote time display by Torpey Controls & Engineering).',
            'The R201 and R221 stereo input modules accept two balanced stereo inputs, A or B, with front-panel trims '
            'for left and right; MONO sums left and right. Stereo balanced insert points come before the FADER and '
            'CHANNEL ON switch (bypass jumpers on the board); CUE is pre-fader, pre-CHANNEL ON, to the cue speaker in '
            'the meter bridge. The signal can be assigned to stereo PROGRAM 1–4 and MONO MIX 1–2, all buses balanced; '
            'the R221 adds front-panel send levels to MONO MIX 1 and 2. A stereo DIRECT output follows CHANNEL ON, '
            'and every switch has an LED. DIP switches on each input set its mode of external control: four control '
            'inputs and four control outputs (CH ON, CH OFF, A SEL, tallies, cue) in eight preset modes.',
            'Followed by the [R2K Cool Grey](Series-R2K-Cool-Grey.md).',
        ],
        evidence=[
            (1998, '"NOV 11, 1998" on the R2K functional diagram and the R202 and R205 functionals'),
            (1999, '32 dated drawings, Jan 21 1999 (R202 schematic) to Dec 1 1999 (R221 issue 2)'),
            (2000, 'R210 studio monitor schematics, Oct 27 2000; R253, Jan 27 2000'),
            (2002, 'guest turret, Jan 2 2002'),
            (2007, 'manual cover: "Renaissance R2K Audio Console, as of May 1st 2007"'),
        ],
        modules=[
            ('R201', 'Stereo Input Module'), ('R221', 'Stereo Input Module, with MONO MIX send levels'),
            ('R202', 'Stereo Output Module'), ('R203', 'Control Room Monitor Module'), ('R204', 'Studio Monitor Module'),
            ('R205', '8 × 2 Stereo Line Selector'), ('R206', 'Utility Module (R206, R206A)'),
            ('R207', 'Stereo Input Module'), ('R208', 'Equalizer Module'), ('R209', 'Clean Feed Module (R209, R209A)'),
            ('R210', 'Studio Monitor Module'), ('R251', 'module address board (12, 20 and 28 channel consoles)'),
            ('R253', 'meter board'), ('R257', 'schematic'), ('Turret', 'Guest turret'), ('Torpey', 'Torpey clock (remote time display)'),
        ],
        modules_from='the section titles of the R2K manual (sections 1–12) and the drawings',
    ),
    'R2K-Cool-Grey': dict(
        title='R2K Cool Grey — Radio Audio Console',
        dirs=['R2K'],
        take=lambda rel: bool(COOL.search(os.path.basename(rel))),
        prev='R2K',
        about=[
            'The Cool Grey is the R2K in its later form: the same console layout and manual (turret, Torpey clock, '
            'console drawings) with the R240 / R250 modules. The R241 Stereo Input Module is "the basic input '
            'channel module for the Cool Grey radio audio console series"; the R242 adds individual level controls on '
            'the two mono sends; the R243 and R244 are the R241 and R242 with a SAS CD8 router control head in place '
            'of the A / B / MONO input selector, taking one stereo input from the SAS router.',
            'Except for the four right-hand positions, any input module fits any slot. Inserts come before the FADER '
            'and CHANNEL ON; the signal goes to any of four stereo program or two mono send buses, all balanced, with '
            'a stereo DIRECT output after the fader. Each input has four programmable control inputs and four outputs '
            '(eight modes), can drive the MUTE A, B, C, AUTO CUE or TIMER RESET buses, and has an RS485 serial port '
            'so some functions can be under serial control.',
        ],
        evidence=[
            (2003, 'Cool Grey manual: the Torpey clock section in its fifth edition, March 2003'),
            (2005, 'R241 input module drawings, issues 5 and 6, to Dec 2005'),
        ],
        modules=[
            ('R241', 'Stereo Input Module (A / B / MONO)'), ('R242', 'Stereo Input Module with mono send levels'),
            ('R243', 'Stereo Input Module with SAS CD8 router control head'), ('R244', 'R242 with SAS CD8 router control head'),
            ('R245', 'Stereo Output Module'), ('R246', 'Control Room Monitor Module'), ('R247', 'Studio Monitor Module'),
            ('R248', 'Utility Module'), ('R249', 'manual section 6'), ('R250', 'Studio Monitor Module (studio I/O board)'),
            ('R258', 'Clean Feed Module'), ('R259', 'Equalizer Module'), ('Turret', 'Guest turret'), ('Torpey', 'Torpey clock'),
        ],
        modules_from='the section titles of the Cool Grey manual and the Input Modules manual',
    ),
}


def load_drive():
    m = {}
    for f in glob.glob(os.path.join(Y, '_catalog', 'drive', '*.json')):
        m.update(json.load(open(f, encoding='utf-8')))
    return m


def original(path):
    """The note's "Original file" (where the file came from), as a Drive-map key."""
    note = path + '.md'
    if os.path.exists(note):
        m = re.search(r'\*\*Original file:\*\* `([^`]+)`', open(note, encoding='utf-8').read(4000))
        if m:
            return '../' + m.group(1)


def drive_of(rel, path, drive):
    for k in (rel, rel.replace(RS + '/', 'Consoles/1990-1999/'), original(path)):
        if k and k in drive:
            return drive[k]


def view(d):
    return f'https://drive.google.com/file/d/{d[0]}/view' + (f'?resourcekey={quote(d[1])}' if len(d) > 1 and d[1] else '')


def thumb(d):
    return f'https://drive.google.com/thumbnail?sz=w480&id={d[0]}' + (f'&resourcekey={quote(d[1])}' if len(d) > 1 and d[1] else '')


def viewer(rel):
    return '../2026/viewer.html?f=' + quote(rel)


def files_of(s):
    out = []
    for d in s['dirs']:
        base = os.path.join(Y, RS, d)
        names = set(os.listdir(base))
        stems = {os.path.splitext(n)[0] for n in names}
        for n in sorted(names):
            stem, ext = os.path.splitext(n)
            if ext.lower() not in SHOWN or '(traced)' in n:
                continue
            if stem.endswith('_small') and stem[:-6] in stems:
                continue                                   # a web thumbnail of the picture beside it
            rel = f'{RS}/{d}/{n}'
            if s['take'](rel):
                out.append((d, n, rel, os.path.join(base, n)))
    return out


def kind(d, n):
    ext = os.path.splitext(n)[1].lower()
    if d in PHOTO_DIRS:
        return 'photo'
    if re.search(r'manual|guide|setup|DIP SWITCH|report|newsletter|Guest Turret|MODIFIED|R201R207|R201 R221 Input|\bone\b|\bfile\b|1st|MKI', n, re.I) \
            or ext in ('.docx', '.doc'):
        return 'manual'
    return 'drawing'


def label(n, d):
    stem, ext = os.path.splitext(n)
    tag = '' if ext.lower() in ('.pdf', '.jpg', '.jpeg', '.png') else f' ({ext[1:].lower()})'
    return re.sub(r'^\d{4} - (?:' + re.escape(d) + r'|R2K|Renaisance) - ', '', stem) + tag


def page(key, s, drive):
    files = files_of(s)
    name = key.replace('-', ' ')
    md = ['---', 'type: "console series"', f'title: "{name}"', 'category: "CONSOLE"',
          f'year: {s["evidence"][0][0]}', 'tags: ["console series", "console", "radio"]', '---', '',
          f'# {s["title"]}', '', '[← Consoles & jobs](Consoles.md)', '', '|  |  |', '|---|---|',
          '| Type | console series |', '| Maker | Ward-Beck Systems Ltd., 841 Progress Avenue, Scarborough, Ontario |',
          f'| Dated evidence | {", ".join(ylink(y) for y, _ in s["evidence"])} |']
    if s.get('prev'):
        md.append(f'| Before it | [{s["prev"].replace("-", " ")}](Series-{s["prev"]}.md) |')
    if s.get('next'):
        md.append(f'| After it | [{s["next"].replace("-", " ")}](Series-{s["next"]}.md) |')
    md += [f'| Folder | [{d}](../2026/{quote(RS + "/" + d)}/) |' for d in s['dirs']]
    md += [f'| Files | {len(files)} |', '']
    md += ['## The series', ''] + [p + '\n' for p in s['about']]
    md += ['## Dated evidence', '', '| Year | Evidence |', '|---|---|'] + [f'| {ylink(y)} | {e} |' for y, e in s['evidence']]
    md += ['', '_File names in the archive start with 1994 for the whole R series folder; the dates above are read from the files themselves._', '']
    if s.get('marks'):
        title, rows, note = s['marks']
        md += ['## Sizes', '', '| Mark | Width | Desk cutout width | Control panel |', '|---|---|---|---|']
        md += [f'| {a} | {b} | {c} | {d} |' for a, b, c, d in rows] + ['', note, '']
    md += ['## Modules', '', f'_From {s["modules_from"]}._', '', '| Module | What it is |', '|---|---|']
    for code, what in s['modules']:
        md.append(f'| {f"[{code}]({code}.md)" if os.path.exists(os.path.join(PAGES, code + ".md")) else code} | {what} |')
    md.append('')
    if s.get('specs'):
        md += ['## Specifications', '', f'_{s["specs_from"]}._', '', '|  |  |', '|---|---|']
        md += [f'| {a} | {b} |' for a, b in s['specs']] + ['']
    groups = {'photo': [], 'manual': [], 'drawing': []}
    for d, n, rel, p in files:
        groups[kind(d, n)].append((d, n, rel, p, drive_of(rel, p, drive)))
    gallery = []
    if groups['photo']:
        md += [f'## Photos ({len(groups["photo"])})', '', '<div class="thumbs">']
        for d, n, rel, p, dv in groups['photo']:
            src = thumb(dv) if dv else '../2026/' + quote(rel)
            href = view(dv) if dv else viewer(rel)
            md.append(f'<a href="{H.escape(href)}"><img loading="lazy" src="{H.escape(src)}" alt="{H.escape(label(n, d))}" '
                      f'data-f="{H.escape(rel)}" data-size="320" onerror="wbsOff(this)">{H.escape(label(n, d))}</a>')
        md += ['</div>', '']
    for k, title in (('manual', 'Manuals and documents'), ('drawing', 'Drawings')):
        if not groups[k]:
            continue
        md += [f'## {title} ({len(groups[k])})', '', '| File | Google Drive | Note |', '|---|---|---|']
        for d, n, rel, p, dv in groups[k]:
            note = f'[note]({viewer(rel + ".md")})' if os.path.exists(p + '.md') else ''
            md.append(f'| [{label(n, d)}]({viewer(rel)}) | {f"[open]({view(dv)})" if dv else ""} | {note} |')
        md.append('')
    md += ['---', FOOT, '']
    return '\n'.join(md), len(files)


def shell():
    """Head and foot of the wiki pages (the archive's paper look), from an existing page."""
    s = open(os.path.join(PAGES, 'Project-R2K.html'), encoding='utf-8').read()
    head = s[:s.index('<h1')]
    tail = s[s.index('<div class="foot">'):]
    return head, tail


def to_html(md, title, src):
    head, tail = shell()
    body = md.split('---\n', 2)[2] if md.startswith('---') else md
    body = body.rsplit('\n---\n', 1)[0]
    h = markdown.markdown(body, extensions=['tables'])
    h = re.sub(r'href="(?!https?:|\.\./)([^"#]+)\.md', r'href="\1.html', h)
    head = re.sub(r'<title>[^<]*</title>', f'<title>{H.escape(title)}</title>', head)
    tail = re.sub(r'generated from [^<]*', f'generated from {src}', tail)
    return head + h + tail


def link_index(made):
    """The "Console series" section in Consoles.md/.html, a link on the project pages."""
    rows = ['## Console series', '', '| Series | What it is | Files |', '|---|---|---|']
    rows += [f'| [{k.replace("-", " ")}](Series-{k}.md) | {SERIES[k]["title"].split(" — ")[1]} | {n} |' for k, n in made]
    sec = '\n'.join(rows) + '\n\n'
    f = os.path.join(PAGES, 'Consoles.md')
    s = open(f, encoding='utf-8').read()
    s = re.sub(r'## Console series\n.*?(?=^## )', '', s, flags=re.S | re.M)
    s = s.replace('## Console models\n', sec + '## Console models\n', 1)
    open(f, 'w', encoding='utf-8').write(s)
    f = os.path.join(PAGES, 'Consoles.html')
    s = open(f, encoding='utf-8').read()
    s = re.sub(r'<h2>Console series</h2>.*?(?=<h2>)', '', s, flags=re.S)
    part = re.sub(r'href="([^"#:]+)\.md', r'href="\1.html', markdown.markdown(sec, extensions=['tables']))
    s = s.replace('<h2>Console models</h2>', part + '\n<h2>Console models</h2>', 1)
    open(f, 'w', encoding='utf-8').write(s)
    for proj, key in (('Project-Renaisance', 'Renaissance'), ('Project-R2K', 'R2K')):
        line = f'Console series: [{key}](Series-{key}.md)' + (' · [R2K Cool Grey](Series-R2K-Cool-Grey.md)' if key == 'R2K' else '')
        for ext in ('.md', '.html'):
            f = os.path.join(PAGES, proj + ext)
            s = open(f, encoding='utf-8').read()
            if 'Console series:' in s:
                continue
            if ext == '.md':
                s = s.replace('[← Consoles & projects](Consoles.md)\n', f'[← Consoles & projects](Consoles.md)\n\n{line}\n', 1)
            else:
                part = re.sub(r'href="([^"#:]+)\.md', r'href="\1.html', markdown.markdown(line)).strip()
                s = s.replace('&amp; projects</a></p>', '&amp; projects</a></p>\n' + part, 1)
            open(f, 'w', encoding='utf-8').write(s)


def main():
    drive = load_drive()
    made = []
    for key, s in SERIES.items():
        md, n = page(key, s, drive)
        base = os.path.join(PAGES, f'Series-{key}')
        open(base + '.md', 'w', encoding='utf-8').write(md)
        open(base + '.html', 'w', encoding='utf-8').write(to_html(md, s['title'], f'Series-{key}.md'))
        made.append((key, n))
        print(f'PAGES/Series-{key}: {n} files')
    link_index(made)


if __name__ == '__main__':
    main()
