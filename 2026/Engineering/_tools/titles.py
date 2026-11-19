"""Read a WBS drawing title block (or a document's heading) into drawing number, device, title and type.

  info = title_info(text, title_block, rel, codes)
  info['display_name']  ->  '14-302-01-003 · IKR-10A · INTERCOM KEY CONTROL & AUDIO · FUNCTIONAL'

Text keeps the wording and capitals of the title block; only OCR damage is repaired
(digits read as letters inside model numbers, words split by a space, Ward-Beck boilerplate).
"""
import re

DWG_RE = re.compile(r'(?<![\d-])([A-D])?\s?((?:14\s?-\s?)?\d{2,6})\s?-\s?(0\d)\s?-\s?(\d{3})[A-Z]?(?!\d)'
                    r'|(?<![\d-])([A-D])?\s?(14\s\d{3})\s(0\d)\s(\d{3})(?!\d)')  # title blocks also write B 14 306 06 001
DOC_TYPES = ['COMPONENT LAYOUT', 'BLOCK DIAGRAM', 'FRONT PANEL', 'PARTS LIST', 'PRICE LIST', 'PRICE SCHEDULE', 'PIN OUTS',
             'PIN OUT', 'SCHEMATIC', 'FUNCTIONAL', 'LAYOUT', 'ASSEMBLY', 'WIRING', 'ARTWORK', 'OUTLINE', 'INTERCONNECT',
             'DRILL', 'SILKSCREEN', 'JACKFIELD', 'TEST PROCEDURE', 'SPECIFICATIONS', 'USER GUIDE', 'MANUAL']
# words a title block uses; split pieces of these are re-joined ("FUNC TIONAL" -> "FUNCTIONAL")
VOCAB = set('''FUNCTIONAL SCHEMATIC AMPLIFIER PREAMPLIFIER ASSEMBLY LAYOUT CONSOLE MODULE CONTROL INTERCOM WIRING
CHANNEL SUBMASTER MASTER MONITOR MONITORING POWER SUPPLY SWITCHER SWITCHING DISTRIBUTION EQUALIZER EQUALISER OSCILLATOR
BACKPLANE INTERFACE CONNECTOR COMPONENT DIAGRAM SELECTOR TALKBACK COMMUNICATION REVERB FOLDBACK COMPRESSOR LIMITER
METER METERING PANEL FRONT REAR TERMINATION JACKFIELD INPUT OUTPUT STEREO PROGRAM ROUTING MATRIX REMOTE ANNOUNCE
MICROPHONE BOOSTER SUMMING CONTROLLER PROCESSOR AUDIO DIGITAL ANALOG CHASSIS FRAME OUTLINE ARTWORK SILKSCREEN'''.split())
BOILER = re.compile(r'^(WARD.?BECK|WBS|SYSTEMS?|LTD\.?|LIMITED|DRN|DRAWN|DATE|CKD|CHECKED|APPROVED|APP|SCALE|TOLS?|ISS|ISSUE|'
                    r'USED ON|MAT.?L|MATERIAL|FINISH|NOTES?|REV|REVISION|SHEET|SH|DWG|NO\.?|TITLE|MOD|ANG|XX|XXX|SIZE|'
                    r'TABLE OF CONTENTS|CONTENTS|INDEX|PAGE|GENERAL|DESIGNED|MANUFACTURED|BY|PLEASE|SEE|REFER|'
                    r'\d+ PROGRESS|PROGRESS AVENUE|SCARBOROUGH|ONTARIO|CANADA|TELEPHONE|TEL|TELEX|FAX|PRINTED IN)\b')
STRIP = re.compile(r'\b(DOCUMENT TITLE|DOCUMENT NUMBER|TABLE OF CONTENTS|GENERAL|WARRANTY|MANUAL ISSUE #?\d+|ISSUE #?\d+|PLEASE REFER TO DRAWING)\b|(?<!\w)[IVX1-9]\)\s*')
PART_REFS = {'CON', 'SW', 'IC', 'TP', 'JP', 'LED', 'CR', 'VR', 'RV', 'FB', 'XTAL', 'PCB', 'REV', 'ISS', 'PAGE', 'NO'}
# device codes as written, even ones the code list does not know: M441M, IKR-4A, SA14-307, D8212F, POD 7
DEVICE_RE = re.compile(r'^(M\d{3,4}[A-Z]{0,3}|SA14-\d{3}[A-Z]?|[A-Z]{1,4}-?\d{1,5}[A-Z]{0,3})$')


def is_device(tok):
    """Shaped like a WBS device code (M441M, IKR-10A, POD7, SA14-288), not a part reference (R111, C57, CON2)"""
    if not (DEVICE_RE.match(tok) and re.search(r'\d', tok)) or DWG_RE.search(tok):
        return False
    letters = re.match(r'[A-Z]+', tok).group(0)
    return letters not in PART_REFS and (letters == 'M' or len(letters) >= 2)


def _load_words():
    try:
        with open('/usr/share/dict/words') as f:
            return {w.strip().upper() for w in f if w.strip().isalpha()}
    except OSError:
        return set()


WORDS = _load_words() | VOCAB


def wordy(line):
    """True when most of a line's longer words are real words (rejects OCR crumbs from photos)"""
    ws = [w.strip('.,()&#/') for w in line.split()]
    ws = [w for w in ws if len(w) >= 3 and w.isalpha()]
    return bool(ws) and sum(w in WORDS for w in ws) >= 0.6 * len(ws)


def drawing_numbers(text):
    """WBS drawing numbers: [size] series-type-sequence, e.g. B181-02-001, 76045-02-004, 14-302-01-003"""
    out = set()
    for m in DWG_RE.findall((text or '').upper()):
        _, s, d, q = m[:4] if m[1] else m[4:]
        out.add(f'{re.sub(r"[ -]+", "-", s.strip())}-{d}-{q}')
    return sorted(out)


def dedupe_words(words):
    """OCR repeats words and phrases: 'MONITOR MONITORLTALKBACK MODULE OUTPUT MONTORLIALKBACK MODULE OUTPUT'"""
    from difflib import SequenceMatcher
    out = []
    for w in words:
        if any(len(w) >= 4 and SequenceMatcher(None, w, o).ratio() >= 0.75 for o in out[-6:]):
            continue
        out.append(w)
    return out


def fix_digits(tok):
    """Inside model numbers OCR reads 1 as l/I and 0 as O: M44lM -> M441M, IKR-IOA -> IKR-10A"""
    m = re.match(r'^([A-Z]{1,4}-?)([0-9lIO|]{2,5})([A-Z]{0,3})$', tok)
    # after a hyphen or in an M-number the letters are digits (IKR-IOA, MI2O4); elsewhere they must already hold one
    if not m or not (re.search(r'\d', m.group(2)) or m.group(1).endswith('-') or m.group(1) == 'M'):
        return tok
    return m.group(1) + m.group(2).translate(str.maketrans('lI|O', '1110')) + m.group(3)


def rejoin(words):
    out = []
    for w in words:
        if out and (out[-1] + w) in VOCAB and out[-1] not in VOCAB:
            out[-1] += w
        else:
            out.append(w)
    return out


def clean_line(line):
    line = re.sub(r'WARD.?BECK\s+SYSTEMS?(\s+LTD\.?)?|\bWBS\b', ' ', line.upper())
    line = re.sub(r'[^A-Z0-9&/#+.,()\' -]', ' ', line)
    words = [fix_digits(w) for w in line.split()]
    if len(words) > 1 and re.fullmatch(r'[A-Z]\)?', words[0]) and re.match(r'(SA14|M\d|\d)', words[1]):
        words = words[1:]  # list markers: "A SA14-280 INPUT AMPLIFIER ASSEMBLY", "A 10X1 STEREO SELECTOR"
    return ' '.join(rejoin(words)).strip(' .,-')


def is_title_block(tb):
    """The bottom-right crop counts only when it shows Ward-Beck title-block furniture"""
    return bool(re.search(r'WARD|BECK|\bWBS\b|\bDRN\b|SCALE|TOLS|\bCKD\b', (tb or '').upper()))


def domain_score(line):
    return sum(w in VOCAB for w in line.split()) + 2 * any(t in line for t in DOC_TYPES)


def title_lines(lines):
    keep = []
    for raw in lines:
        line = clean_line(raw)
        letters = sum(c.isalpha() for c in line)
        if letters < 4 or BOILER.match(line) or DWG_RE.search(line) and letters < 8:
            continue
        line = STRIP.sub(' ', line)
        tokens = line.split()
        if len(tokens) <= 2 and any(DEVICE_RE.match(t) and re.search(r'\d', t) for t in tokens):  # a model-number line: IKR-10A
            keep.append(line)
            continue
        if re.search(r'REVIS|UNDEFINED|\bISSUE\b|\bPAGE\b', line):  # revision and page furniture, not a title
            continue
        if not wordy(line) or len(line) > 48:  # OCR crumbs, or body text rather than a title
            continue
        line = re.sub(r'\s+', ' ', DWG_RE.sub('', line)).strip(' .,-')
        tokens = line.split()
        if tokens and sum(len(t) <= 2 for t in tokens) > 0.4 * len(tokens):  # drawing labels: "5 OSCILLATOR BON 2"
            continue
        if line and line not in keep:
            keep.append(line)
    # a title block holds the title on its last lines; labels from the drawing above come first
    if len(keep) > 3:
        keep = [k for k in keep if domain_score(k) or any(DEVICE_RE.match(t) for t in k.split())][-3:] or keep[-3:]
    return keep[:4]


def title_info(text, title_block, rel, codes, kind=''):
    """codes: {UPPER or hyphen-free code: canonical code}; kind from the tagger (price lists are titled as such)"""
    tb_ok = is_title_block(title_block)
    source = (title_block if tb_ok else '') or ''
    dwgs = drawing_numbers(source) or drawing_numbers(rel) or drawing_numbers(text)
    lines = title_lines(source.splitlines()) if source else []
    if not lines and kind == 'price list':
        lines = ['PRICE SCHEDULE' if 'PRICE SCHEDULE' in (text or '').upper() else 'PRICE LIST']
    if not lines:  # documents: the best heading among the first lines - domain words, a type word or a device code
        heads = title_lines((text or '').splitlines()[:40])
        if heads:
            best = max(heads, key=lambda h: (domain_score(h) + 2 * any(fix_digits(w) in codes for w in h.split()), -heads.index(h)))
            # labels and listings ("JP1 JP2", "SOLID LINE", "ITEM QUANTITY REFERENCE PART") are not titles
            if domain_score(best) or any(fix_digits(w) in codes or is_device(fix_digits(w)) for w in best.split()):
                lines = [best]
    title = ' '.join(dedupe_words(' '.join(lines).split()))
    device = ''
    path_words = [fix_digits(w) for part in rel.split('/') for w in clean_line(part).split()]
    candidates = [fix_digits(w.strip('(),')) for w in title.split()] + path_words[::-1]  # file name first, then folders
    for key in candidates:  # a known code first, then anything shaped like a device code
        if key in codes or key.replace('-', '') in codes:
            device = key
            break
    if not device:
        device = next((k for k in candidates if is_device(k)), '')
    doc_type = next((t for t in DOC_TYPES if t in title), '') or next((t for t in DOC_TYPES if t in (text or '').upper()[:3000]), '')
    if kind == 'price list':
        doc_type = title if title in ('PRICE LIST', 'PRICE SCHEDULE') else doc_type
    rest = title
    for part in (device, doc_type):
        if part:
            rest = re.sub(rf'(?<![A-Z0-9]){re.escape(part)}(?![A-Z0-9])', ' ', rest)
    if device:  # the same device written another way: POD5 / POD 5, IKR10A / IKR-10A
        flat = re.sub(r'[\s-]', '', device)
        rest = ' '.join(w for w in re.split(r'(?<=\d)\s+|\s+(?=[A-Z]{2})', rest) if re.sub(r'[\s-]', '', w) != flat)
    rest = re.sub(r'\s+', ' ', rest).strip(' .,-')
    name = ' · '.join(p for p in (dwgs[0] if dwgs else '', device, rest, doc_type) if p)
    return {'dwg_no': dwgs[0] if dwgs else '', 'device': device, 'title': title, 'doc_type': doc_type,
            'display_name': name or rel.rsplit('/', 1)[-1].rsplit('.', 1)[0], 'title_source': 'title block' if lines and tb_ok else 'text' if lines else 'file name'}


def safe_filename(name, limit=120):
    """A display name made safe for a file or folder name (keeps &, #, commas)."""
    name = name.replace(' · ', ' - ').replace('/', '-')
    return re.sub(r'[\\:*?"<>|]', '', name)[:limit].strip(' .-')
