#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""Where a file goes inside a module folder (2026/Modules/<CATEGORY>/<Mxxx>/), shared by every archive script.

    <Mxxx>/README.md, index.html          the module's front page (stay at the top)
    <Mxxx>/RTO.json                        the module's RTO-144 edge connector, pin by pin (tools/module_extras.py)
    <Mxxx>/SCHEMATICS/                     drawings: schematics, component layouts, mechanical, CAD, tracings, and
                                           "<drawing> (EXTRACTED).svg": the vectors traced from each scanned drawing
    <Mxxx>/MECHANICAL/                     mechanical drawings: front panels, cover plates, metalwork (-03-), and
                                           "<Mxxx> - front panel.svg", the front panel as vectors
    <Mxxx>/PINOUTS/                        pinouts, connector layouts and rear views, RTO-144 connection sheets
    <Mxxx>/KICAD/                          KiCad: a schematic from each extracted electrical drawing, the module symbol,
                                           its PCB projects (Engineering/PCB)
    <Mxxx>/MANUALS/                        manuals, manual pages, price lists, connection sheets, documents, ads
    <Mxxx>/PHOTOS/                         photographs of the device
    <Mxxx>/SOFTWARE/                       program listings, firmware, the plugin/ crate
    <Mxxx>/OCR/                            the .md note (date, origin, OCR text) of every file above: OCR/<file name>.md

Import it (`sys.path` gets tools/) and use kind_of(), note_for() and module_files().
"""
import os
import re

KINDS = ('SCHEMATICS', 'MECHANICAL', 'PINOUTS', 'MANUALS', 'PHOTOS', 'SOFTWARE', 'KICAD', 'OCR')
TOP = {'README.md', 'index.html', '.gitignore', '.git', 'RTO.json'}

SOFTWARE_EXT = {'.txt', '.hex', '.bin', '.asm', '.s', '.src', '.c', '.h', '.bas', '.lst', '.s19', '.rom', '.mot', '.ihx'}
CAD_EXT = {'.dwg', '.dxf', '.pcb', '.dsn', '.brd', '.sch', '.schdoc', '.pcbdoc', '.gbr', '.ger', '.kicad_pcb', '.kicad_sch'}
SOFTWARE_WORDS = re.compile(r'\b(program listing|listing|firmware|software|eprom|e?prom dump|source code|#esp_out)\b', re.I)
# WBS drawing numbers: 460-04-008, B460-04-008, 4-126-02-001, 8207-02-001, 724-06-001
DRAWING_NO = re.compile(r'(?<![\dA-Z])[A-D]? ?\d{1,4}-\d{1,4}-0\d-\d{3}(?!\d)|(?<![\dA-Z])[A-D]? ?\d{3,6}-0?\d{2}-\d{3}(?!\d)', re.I)
DRAWING_WORDS = re.compile(r'\b(schem\w*|component layout|layout|pinout|pin-?out|wiring|drawing|assembly|assy|pcb|'
                           r'circuit|block diagram|silk\w*|artwork|panel drawing|mechanical|outline|pin ?outs?|functional|diagram|drc)\b', re.I)
# The drawing number decides, as in the WBS data shuffler: the # in XXX-#-YYY is the kind of drawing
TYPE_NO = re.compile(r'(?<![\dA-Z])(?:[A-D])?\s?(?:(?:\d{1,2}\s?[-_]\s?)?\d{2,6})\s?[-_]\s?(0[1-9])\s?[-_]\s?\d{3}(?!\d)', re.I)
BY_TYPE = {'01': 'SCHEMATICS',   # functional / block diagram
           '02': 'SCHEMATICS',   # schematic
           '03': 'MECHANICAL',   # mechanical: metalwork, escutcheons, chassis
           '04': 'MECHANICAL',   # layout / outline: front panels (connector layouts and rear views: PINOUTS)
           '05': 'MECHANICAL',   # assembly
           '06': 'SCHEMATICS',   # component layout (the PCB)
           '07': 'SCHEMATICS',   # parts list
           '08': 'MANUALS',      # test procedure
           '09': 'SCHEMATICS'}   # wiring
MECH_NO = re.compile(r'(?<![\dA-Z])[A-D]? ?\d{1,4}-(?:\d{1,4}-)?03-\d{3}(?!\d)', re.I)
MECH_WORDS = re.compile(r'\b(front ?panels?|face ?plates?|cover plates?|sub ?panels?|panel drawing|mechanical|metal\w*|'
                        r'chassis|brackets?|drill\w*|alumin\w*|machin\w*|extrusions?|engrav\w*|lid|card guides?|'
                        r'handles?|silk ?screen\w*|escutcheons?|dimension\w*|bend rad\w*|cut ?outs?|frame|enclosure|'
                        r'housing|rack ?mount\w*|hardware)\b', re.I)
ELEC_WORDS = re.compile(r'\b(schem\w*|circuit|functional|block diagram|wiring|component layout|pcb)\b', re.I)
PINOUT_WORDS = re.compile(r'\b(pin ?-?outs?|pinouts?|rto-?144|connector (layout|outline|wiring|pin\w*)|rear view|'
                          r'connections?|strapping)\b', re.I)
NOT_DRAWING = re.compile(r'\bprice list\b|\bmanual\b', re.I)
MANUAL_WORDS = re.compile(r'(^|\s)-\s(DOC|P\d{1,3}|PRICE LIST|AD)(\s-|$|\s\(\d+\)$)|\bpage_?\d|\bpg \d|\b(manual|brochure|spec sheet|'
                          r'instruction|index|toc|price|catalog\w*|bulletin|data sheet|leaflet)\b', re.I)
PHOTO_WORDS = re.compile(r'\b(front|back|rear|side|top|bottom|inside|internal|photo\w*|pic|picture|promo|'
                         r'wbsps - module)\b', re.I)
IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.tif', '.tiff', '.bmp', '.webp', '.heic'}
PHOTO_NAME = re.compile(r'\b(IMG|DSC|DSCN|DSCF|PXL|P\d{7})_?\d{3,}|\b\d{8}_\d{6}\b|\b\d{4}-\d\d-\d\d \d\d[_.]\d\d[_.]\d\d\b', re.I)
DOC_EXT = {'.wp', '.wpd', '.doc', '.docx', '.rtf', '.odt'}
MANUAL_NAME = re.compile(r'\b(test procedures?|circuit description|information sheet|data ?sheet)\b', re.I)


def _manual_list():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'module_manuals.txt'), encoding='utf-8') as fh:
            return {ln.rstrip('\n') for ln in fh if ln.strip() and not ln.startswith('#')}
    except OSError:
        return set()


MANUAL_FILES = _manual_list()   # pages found by their content to be manual pages (tools/module_manuals.txt)
ORIGIN = re.compile(r'^- \*\*Original file:\*\* `([^`]*)`', re.M)


def is_note(name):
    return name.endswith('.md') and name not in TOP


def traced_source(name, siblings):
    """'X (traced).dxf' / '.json' -> the scan 'X.<ext>' it was traced from, if it is there."""
    stem = re.sub(r' \((traced|EXTRACTED)\)\.[^.]+$', '', name)
    for st in (stem, re.sub(r' p\d+$', '', stem)):    # a PDF's pages: "X p3 (traced).dxf" is from X.pdf
        for s in siblings:
            if s != name and os.path.splitext(s)[0] == st and not s.endswith('.md') and '(traced)' not in s \
                    and '(EXTRACTED)' not in s:
                return s
    return None


def colourful(path):
    """A colour photograph rather than a paper scan: scans of paper read almost no saturation (mean S < 3)."""
    try:
        from PIL import Image, ImageStat
        with Image.open(path) as im:
            im.draft('RGB', (160, 160))
            return ImageStat.Stat(im.convert('HSV').resize((96, 96)).getchannel('S')).mean[0] > 12
    except Exception:
        return False


def kind_of(name, origin='', siblings=(), path=None):
    """The folder a (non-note) module file belongs in. `origin` is the note's 'Original file' path."""
    if name in TOP:
        return None
    if name == 'plugin':
        return 'SOFTWARE'
    if '(traced)' in name or name.endswith('(EXTRACTED).svg'):
        src = traced_source(name, siblings)
        return kind_of(src, '', (), path and os.path.join(os.path.dirname(path), src)) if src else 'SCHEMATICS'
    stem, ext = os.path.splitext(name)
    ext = ext.lower()
    # Anything that is a manual goes in MANUALS: documents, and pages known to be manual pages
    if name in MANUAL_FILES or ext in DOC_EXT or MANUAL_NAME.search(stem):
        return 'MANUALS'
    if ext.startswith('.kicad_') or ext in ('.kicad_sym', '.kicad_pro', '.kicad_prl'):
        return 'KICAD'
    if PINOUT_WORDS.search(stem) and ext not in CAD_EXT:
        return 'PINOUTS'
    t = TYPE_NO.search(stem)
    if t and ext not in SOFTWARE_EXT and t.group(1) in BY_TYPE:
        k = BY_TYPE[t.group(1)]
        if t.group(1) in ('03', '04') and PINOUT_WORDS.search(stem):
            return 'PINOUTS'
        return k
    if ext not in ('.pcb', '.dsn', '.brd', '.sch', '.schdoc', '.pcbdoc', '.gbr', '.ger', '.txt') and \
            (MECH_NO.search(stem) or MECH_WORDS.search(stem) and not ELEC_WORDS.search(stem) or
             ext == '.dwg' and not ELEC_WORDS.search(stem)):
        return 'MECHANICAL'
    if ext in CAD_EXT or ext == '.txt' and re.search(r'DRC|\.ERR$', stem, re.I):
        return 'SCHEMATICS'
    if ext in SOFTWARE_EXT or SOFTWARE_WORDS.search(stem):
        return 'SOFTWARE'
    if not NOT_DRAWING.search(stem) and (DRAWING_NO.search(stem) or DRAWING_WORDS.search(stem)):
        return 'SCHEMATICS'
    if MANUAL_WORDS.search(stem) or ext not in IMAGE_EXT:
        return 'MANUALS'
    if '/RAW Photos/' in origin and '/ADVERTISEMENTS' not in origin or PHOTO_NAME.search(stem) or \
            PHOTO_WORDS.search(stem) or re.search(r'/(PHOTOS?|Pictures)/', origin, re.I) or (path and colourful(path)):
        return 'PHOTOS'
    return 'MANUALS'


def origin_of(note_path):
    try:
        with open(note_path, encoding='utf-8', errors='replace') as fh:
            m = ORIGIN.search(fh.read(6000))
        return m.group(1) if m else ''
    except OSError:
        return ''


def module_dir_of(path):
    """…/Modules/<CAT>/<M>/[KIND/]file -> …/Modules/<CAT>/<M> (or None outside a module folder)."""
    parts = path.replace(os.sep, '/').split('/')
    for i in range(len(parts) - 3, -1, -1):
        if parts[i] == 'Modules' and i + 3 <= len(parts) - 1:
            return '/'.join(parts[:i + 3])
    return None


def note_for(path):
    """The .md note of a file. Module files: <M>/OCR/<name>.md; everywhere else: beside it."""
    p = path.replace(os.sep, '/')
    head, name = os.path.split(p)
    if os.path.basename(head) in KINDS[:-1] and module_dir_of(p) == os.path.dirname(head):
        return f'{os.path.dirname(head)}/OCR/{name}.md'
    return p + '.md'


def note_target(note):
    """The inverse: <M>/OCR/<name>.md -> the file it describes (searched in the other kind folders), else note minus .md."""
    p = note.replace(os.sep, '/')
    head, name = os.path.split(p)
    base = name[:-3]
    if os.path.basename(head) == 'OCR':
        mod = os.path.dirname(head)
        for k in KINDS[:-1]:
            if os.path.exists(f'{mod}/{k}/{base}'):
                return f'{mod}/{k}/{base}'
        return f'{mod}/{base}'
    return p[:-3]


def module_files(moddir):
    """Every archive file of a module (not notes, not the front page), as (kind, name, path), either layout."""
    out = []
    for name in sorted(os.listdir(moddir)):
        p = os.path.join(moddir, name)
        if name in KINDS and os.path.isdir(p):
            if name == 'OCR':
                continue
            for n in sorted(os.listdir(p)):
                if not n.startswith('.') and n != 'README.md':
                    out.append((name, n, os.path.join(p, n)))
        elif name not in TOP and not is_note(name) and not name.startswith('.'):
            out.append((None, name, p))
    return out
