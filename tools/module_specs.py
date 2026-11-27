#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""A module's TECHNICAL DATA and CIRCUIT DESCRIPTION, read from its own manuals, as data in its folder:

  <module>/Specifications.json       every line of the technical data sheet: name, the value as printed, the numbers
                                     and units in it, sub-items (Line: / Mic: …), and the manual page it was read from
  <module>/CircuitDescription.json   the circuit description: its paragraphs (under their sub-headings), and the pages

Both come from the archive's OCR (wbs_timeline.db pages; the spell-checked text where there is one), the manuals in
the module's own folder first. The sheet with the most lines that names the module wins; the other manuals that carry
one are listed under "also_in". OCR slips that are always the same (t0 → to, d8m → dBm, mpedance → impedance, letters
spaced apart) are put right; the rest is kept as read, with the page to check it against.
tools/make_module_readmes.py shows both in the README.

    python3 tools/module_specs.py [Products/Modules/CAT/M ...]
"""
import glob
import json
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
Y2026 = os.path.join(ROOT, '2026')
DB = os.path.join(Y2026, 'timelines', 'wbs_timeline.db')
WORDS = set()
for p in ('/usr/share/dict/american-english', '/usr/share/dict/british-english'):
    try:
        WORDS |= {w.strip().lower() for w in open(p, encoding='utf-8', errors='ignore') if w.strip() and "'" not in w}
    except OSError:
        pass
WORDS |= {'db', 'dbm', 'dbu', 'hz', 'khz', 'mhz', 'ma', 'vdc', 'vac', 'ohms', 'thd', 'ein', 'smpte', 'rms', 'pcb', 'vu',
          'ppm', 'imd', 'cmrr', 'mic', 'eq', 'pk', 'kg', 'mm', 'va', 'dc', 'ac', 'max', 'min', 'nom', 'typ'}

TD = re.compile(r'^\W*(?:T\s*E\s*C\s*H\s*N\s*I\s*C\s*A\s*L\s*D\s*A\s*[T7I]\s*A|S\s*P\s*E\s*C\s*I\s*F\s*I\s*C\s*A\s*T\s*I\s*O\s*N\s*S)\b', re.I)
CD = re.compile(r'^\W*(?:\d+(?:\.\d+)*\s*)?C\s*I\s*R\s*C\s*U\s*I\s*T\s+D\s*E\s*S\s*C\s*R\s*I\s*P\s*T\s*I\s*O\s*N\b', re.I)
STOP = re.compile(r'^\W*(?:\d+(?:\.\d+)*\s*)?(?:INSTALLATION|MAINTENANCE|ALIGNMENT|ADJUSTMENTS?|TEST\s+PROCEDURES?|PARTS\s+LISTS?|'
                  r'OPERATION|OPERATING\s+INSTRUCTIONS|DRAWINGS|SCHEMATICS?|WARRANTY|UNPACKING|TECHNICAL\s+DATA|'
                  r'SPECIFICATIONS|GENERAL\s+DESCRIPTION|INTRODUCTION|SERVICE|TROUBLE\s*SHOOTING|CALIBRATION)\b')
JUNK_LINE = re.compile(r'^\W*\S{1,3}\W*$|://|\btp\s+ht\b|S\s*Y\s*S\s*T\s*E\s*M\s*S\s+L\s*[T7I]\s*[DO0]|W[AR]\w*\s*-?\s*B\w*K\s+SYS\w*|^\W*\d{1,2}\s*-\s*\d{1,2}\W*$|^\W*(?:page\s*)?\d{1,3}\W*$|'
                       r'wbsps|kuzub|www\.|http|e-?mail|website|^\W*rev\b|^\W*drn\b|^\W*iss(?:ue)?\b', re.I)
NOT_LABEL = {'website', 'email', 'rev', 'note', 'notes', 'technicaldata', 'specifications', 'drn', 'price', 'fig', 'caution',
             'pleasenote', 'documentissue', 'wardbeckpartnumber', 'blank', 'contactourservicedepartment', 'drawings',
             'circuitdescriptionpartslistdrawings', 'unpacking', 'installation', 'operation', 'features', 'eprom', 'type'}
LABEL_FIX = [(r'\bmpedance', 'Impedance'), (r'\bImpedance', 'Impedance'), (r'Dis\s*tortion', 'Distortion'), (r'\s+', ' ')]


def squash_spaced(s):
    """'Freq ue ncy Re sponse' → 'Frequency Response': fragments rejoined where together they make a word."""
    toks, out, i = s.split(' '), [], 0
    while i < len(toks):
        best = None
        for j in range(min(len(toks), i + 6), i + 1, -1):
            if not all(re.fullmatch(r'[A-Za-z]+', t) for t in toks[i:j - 1]) or not re.fullmatch(r'[A-Za-z]+[.,:;)]?', toks[j - 1]):
                continue
            w = ''.join(toks[i:j])
            core = re.sub(r'[^A-Za-z]', '', w).lower()
            if len(core) > 2 and core in WORDS and not all(re.sub(r'[^A-Za-z]', '', t).lower() in WORDS and len(t) > 2 for t in toks[i:j]):
                best = j
                break
        if best:
            out.append(''.join(toks[i:best]))
            i = best
        else:
            out.append(toks[i])
            i += 1
    return ' '.join(out)


FIXES = [
    (r'(?<=\d)\s*[tTI][0oO]\s*(?=[-+]?\d)', ' to '), (r'\b[tTI][0oO]\b', 'to'), (r'\bd8m\b|\bdBmn\b|\bd8rn\b|\bdBrn\b', 'dBm'),
    (r'\bd8\b', 'dB'), (r'\bk[tH][lI1]?z\b|\bkHZ\b|\bktlz\b', 'kHz'), (r'\bH[zZ2]\b', 'Hz'), (r'\bo[hn][mr]n?s\b|\bohrns\b', 'ohms'),
    (r'\boutpui\b', 'output'), (r'\boulput\b', 'output'), (r'\b[IJ]ow\b', 'low'), (r'\bTevel\b', 'level'), (r'\bTHO\b', 'THD'),
    (r'(?<=\d)[oO](?=[\doO]*\b)', '0'), (r'(?<=\d)[oO]\b', '0'), (r'(?<=\d)[oO](?=[\doO]*\b)', '0'),
    (r'(?<=\d) ?, ?(?=\d{3}\b)', ','), (r'(?<=\d) \. (?=\d)', '.'),
    (r'(?<=\d) \.(?=\d)', '.'), (r'(?<=\d)\. (?=\d)', '.'), (r'\bro\.(?=\d)', '±0.'), (r'(?<=\s)\+(?=0\.\d+ dB)', '±'),
    (r'(?<=\d) (?=\d (?:dBm|dB|Hz|kHz|ohms)\b)', ''), (r'(?<=[+-]\d) (?=\d\b)', ''), (r'(?<=[+-]) (?=\d)', ''),
    (r'\s+([.,;:)])', r'\1'), (r'\(\s+', '('), (r'\s{2,}', ' '), (r'\b(\w+)- (\w+)', r'\1\2'),
]


def fix(s):
    s = squash_spaced(re.sub(r'\s+', ' ', s).strip())
    for a, b in FIXES:
        s = re.sub(a, b, s)
    return s.strip(' _').rstrip('-').strip()


UNIT = r'(dBm|dBu|dBV|dB|kHz|MHz|Hz|kohms?|ohms?|Ω|mA|mV|volts?(?:\s+(?:ac|dc))?|VA\b|V\s?(?:ac|dc|rms)\b|V\b|A\b|watts?|W\b|%|ms\b|µs|us\b|' \
       r'seconds?|sec|pounds?|lbs?|kg|mm|inches|in\.|"|degrees\s+Celsius|°C)'
NUM = r'[-+]?\d+(?:,\d{3})*(?:\.\d+)?'
QTY = re.compile(r'(±|\+/-)?(' + NUM + r')(?:\s*(?:to|-)\s*(' + NUM + r'))?\s*' + UNIT + r'(?![A-Za-z])', re.I)


def quantities(s):
    out = []
    num = lambda x: (lambda v: int(v) if v.is_integer() else v)(float(x.replace(',', '')))
    for m in QTY.finditer(s):
        unit = re.sub(r'\s+', ' ', m.group(4))
        if m.group(3):   # a range: 20 Hz to 20 kHz has its own units; "+18 to -6 dB" shares one
            out.append({'from': num(m.group(2)), 'to': num(m.group(3)), 'unit': unit})
            continue
        q = {'value': num(m.group(2)), 'unit': unit}
        if m.group(1):
            q['tolerance'] = True
        out.append(q)
    return out


def key_of(name):
    """The field name: input_impedance for 'Input impedances' too, so modules compare on the same key."""
    k = re.sub(r'_+', '_', re.sub(r'[^a-z0-9]+', '_', name.lower())).strip('_')
    return re.sub(r'(impedance|level|sensitivit(?:y|ie)|output|input|requirement)s\b', lambda m: m.group(1), k).replace('sensitivitie', 'sensitivity')


SHORT = {'a', 'of', 'to', 'in', 'at', 'on', 'or', 'by', 'dc', 'ac', 'db', 'eq', 'vu', 'mic', 'pad', 'and', 'off'}


def segment(letters):
    """'sourceimpedances' → 'source impedances' (fewest dictionary words), or None."""
    best = [None] * (len(letters) + 1)
    best[0] = []
    for i in range(1, len(letters) + 1):
        for j in range(max(0, i - 18), i):
            w = letters[j:i]
            ok = (len(w) >= 3 and (w in WORDS or (w.endswith('s') and w[:-1] in WORDS))) or w in SHORT
            if best[j] is not None and ok and (best[i] is None or len(best[j]) + 1 < len(best[i])):
                best[i] = best[j] + [w]
    return ' '.join(best[-1]) if best[-1] else None


def canonical(raw):
    """A garbled label snapped to the label the sheets use ('I np U l Impedance' → 'Input impedance'), or None."""
    import difflib
    k = re.sub(r'[^a-z]', '', raw.lower().replace('mpedance', 'impedance').replace('iimpedance', 'impedance'))
    if len(k) < 4:
        return None
    pool = KNOWN | {x + 's' for x in KNOWN if not x.endswith('s')}
    hit = difflib.get_close_matches(k, pool, n=1, cutoff=0.8)
    if not hit:
        return None
    plural = hit[0] not in KNOWN
    seg = segment(hit[0][:-1] if plural else hit[0])
    if seg and plural:
        seg = seg[:-1] + 'ies' if seg.endswith('y') else seg + 's'
    return seg[:1].upper() + seg[1:] if seg else None


def label_of(raw):
    can = canonical(raw)
    if can:
        return can
    seg = segment(re.sub(r'[^a-z]', '', raw.lower().replace('mpedance', 'impedance').replace('iimpedance', 'impedance')))
    if seg and not re.search(r'[0-9()/&]', raw):
        return seg[:1].upper() + seg[1:]
    n = squash_spaced(re.sub(r'\s+', ' ', raw).strip())
    for a, b in LABEL_FIX:
        n = re.sub(a, b, n)
    n = n.strip(' .-')
    return n[:1].upper() + n[1:]


KNOWN = {'frequencyresponse', 'noise', 'ambienttemperature', 'harmonicdistortion', 'totalharmonicdistortion', 'powerrequirements',
         'powerrequirement', 'dimensions', 'sourceimpedance', 'sourceimpedances', 'outputimpedance', 'outputimpedances',
         'loadimpedance', 'loadimpedances', 'gain', 'weight', 'inputimpedance', 'inputimpedances', 'phasing', 'inputlevel',
         'inputlevels', 'outputlevel', 'outputlevels', 'commonmoderejection', 'commonmoderejectionratio', 'inputsensitivity',
         'inputsensitivities', 'outputisolation', 'channelseparation', 'crosstalk', 'attacktime', 'releasetime',
         'compressionratio', 'dynamicrange', 'headsetoutput', 'speakeroutput', 'circuitprotection', 'meterballistics',
         'returnloss', 'phaseshift', 'temperaturerange', 'equalizationtracking', 'attenuatortracking', 'lineregulation',
         'loadregulation', 'rippleandnoise', 'distortion', 'mounting', 'finish', 'accessories', 'outputoffset',
         'commonmodevoltage', 'minimumloadimpedance', 'frequencytolerance', 'slope', 'sensitivity', 'stability', 'protection'}


def known_label(l):
    k = re.sub(r'[^a-z]', '', l.lower().replace('mpedance', 'impedance').replace('iimpedance', 'impedance'))
    return k in KNOWN and len(l.strip()) < 40


LABEL = re.compile(r'^\s*([A-Za-z][A-Za-z0-9 .&/()\'-]{1,60}?)\s*[:;]\s*(.*)$')


def parse_sheet(text):
    """The label: value lines under TECHNICAL DATA, until the next section."""
    lines = text.splitlines()
    at = next((i for i, l in enumerate(lines) if TD.search(l)), None)
    if at is None:
        return None, []
    title = ''
    specs, cur, sub = [], None, None
    for l in lines[at + 1:]:
        if STOP.search(l) and not TD.search(l) or CD.search(l):
            break
        if not l.strip() or JUNK_LINE.search(l):
            continue
        m = LABEL.match(l)
        if not m:   # a label the OCR lost the colon of, alone on its line or ahead of its value
            for n in range(min(5, len(l.split())), 0, -1):
                head = ' '.join(l.split()[:n])
                if known_label(head):
                    m = re.match(r'(\s*)(.*)', l)
                    m = LABEL.match(head + ': ' + ' '.join(l.split()[n:]))
                    break
        k = re.sub(r'[^a-z]', '', (m.group(1) if m else '').lower())
        if m and k and k not in NOT_LABEL and len(squash_spaced(m.group(1)).split()) <= 6:
            name, val = label_of(m.group(1)), m.group(2).strip()
            indented = len(l) - len(l.lstrip()) > 8
            short = len(name.split()) <= 3 and len(name) <= 22
            if cur and short and (indented or (not cur['text'] and not cur.get('items')) or (cur.get('items') and short and len(name) < 14)) \
                    and name.lower() not in ('noise', 'gain', 'weight', 'phasing', 'dimensions'):
                sub = {'name': name, 'text': val}
                cur.setdefault('items', []).append(sub)
            else:
                cur, sub = {'name': name, 'text': val}, None
                specs.append(cur)
            continue
        if not specs:
            if not title and re.search(r'R?M\s?\S{3,5}', l):
                title = fix(l)
            continue
        tgt = sub or cur
        tgt['text'] = (tgt['text'] + ' ' + l.strip()).strip()
    out = []
    for s in specs:
        s['text'] = fix(s['text'])
        for it in s.get('items', []):
            it['text'] = fix(it['text'])
            it['quantities'] = quantities(it['text'])
            it['key'] = key_of(it['name'])
        if not s['text'] and not s.get('items'):
            continue
        s['key'] = key_of(s['name'])
        if 'response' in s['key'] or 'tracking' in s['key']:   # the sheets print ±; OCR reads it as + (or ro)
            s['text'] = re.sub(r'^\+(?=\d+(?:\.\d+)?\s*dB)', '±', s['text'])
        s['quantities'] = quantities(s['text'])
        out.append({k: s[k] for k in ('name', 'key', 'text', 'quantities', 'items') if k in s and s[k] != []})
    return title, out


def paragraphs(lines):
    """OCR lines → paragraphs (and sub-headings), hyphenated line ends joined."""
    out, buf = [], []

    def flush():
        if buf:
            t = fix(re.sub(r'-\s+(?=[a-z])', '', ' '.join(buf)))
            if len(t) > 2:
                out.append({'text': t})
            buf.clear()
    for l in lines:
        s = l.strip()
        if not s or JUNK_LINE.search(s):
            flush()
            continue
        if re.search(r'\bR?M\s?[0-9O]{3,4}', s) and s.upper() == s and len(s) < 60:   # the module's title, on every page
            flush()
            continue
        if len(s) < 60 and (s.isupper() or re.match(r'^\d+(\.\d+)+\s+[A-Z]', s)) and not s.endswith('.') and len(s.split()) <= 8:
            flush()
            out.append({'heading': fix(s)})
            continue
        buf.append(s)
        if s.endswith(('.', ':')) and len(s) < 55:
            flush()
    flush()
    # a heading takes the paragraphs under it; the section title and the module title repeated on each page are dropped
    sec, res = None, []
    for p in out:
        if 'heading' in p and (CD.search(p['heading']) or re.search(r'\bR?M\s?\w{3,5}\b.*\b(?:MODULE|AMPLIFIER|UNIT|PANEL|SUPPLY|'
                                                                     r'EQUALI[ZS]ER|FILTER|METER|LIMITER|COMPRESSOR|OSCILLATOR)', p['heading'], re.I)):
            continue
        if 'paragraphs' not in p and 'heading' not in p and CD.search(p['text']) and len(p['text']) < 30:
            continue
        if 'heading' in p:
            sec = {'heading': p['heading'], 'paragraphs': []}
            res.append(sec)
        else:
            if sec is None:
                sec = {'heading': None, 'paragraphs': []}
                res.append(sec)
            sec['paragraphs'].append(p['text'])
    return [s for s in res if s['paragraphs']]


def quality(text):
    """The share of its words that are words: how well the OCR read it."""
    ws = [w.lower() for w in re.findall(r'[A-Za-z]{3,}', text)]
    return sum(w in WORDS for w in ws) / len(ws) if ws else 0


def parse_circuit(pages):
    """pages: [(page, text)] of one manual, in order. The CIRCUIT DESCRIPTION section, over as many pages as it runs."""
    got, used, on = [], [], False
    for pg, text in pages:
        lines = text.splitlines()
        start = 0
        if not on:
            at = next((i for i, l in enumerate(lines) if CD.search(l) and len(l.strip()) < 70), None)
            if at is None:
                continue
            on, start = True, at + 1
        end = next((i for i in range(start, len(lines)) if STOP.search(lines[i]) and len(lines[i].strip()) < 60), None)
        got += lines[start:end]
        used.append(pg)
        if end is not None or len(used) >= 6:
            break
    secs = paragraphs(got)
    body = ' '.join(p for s in secs for p in s['paragraphs'])
    words, q = len(body.split()), quality(body)
    return (secs, used, words, q) if words >= 40 and q >= 0.6 else (None, [], 0, 0)


CODEISH = str.maketrans({'O': '0', 'o': '0', 'S': '5', 'I': '1', 'l': '1'})


def names_code(title, code):
    t = re.sub(r'\s+', '', title.upper())
    digits = re.escape(code[1:] if code.startswith('M') else code[2:])
    return code.upper() in t or re.search(r'R?M' + digits + r'(?![0-9A-Z])', t.translate(CODEISH)) is not None or \
        code.upper() in t.translate(CODEISH)


def main():
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    spell = {}
    dirs = [os.path.abspath(a) for a in sys.argv[1:]] or sorted(
        p for p in glob.glob(os.path.join(ROOT, 'Products', 'Modules', '*', '*')) if os.path.isdir(p) and re.match(r'R?M\d', os.path.basename(p)))
    n_spec = n_circ = 0
    for d in dirs:
        code = os.path.basename(d)
        rel = os.path.relpath(d, Y2026).replace(os.sep, '/')
        # the module's documents: OCR'd wherever they were read, found by what they are (sha256 → where they live now)
        docs = con.execute("SELECT DISTINCT d.id, f.dest FROM files f JOIN documents d ON d.sha256 = f.sha256 WHERE f.dest LIKE ?",
                           (rel + '/%',)).fetchall()
        seen = {i for i, _ in docs}
        docs += [(i, p) for i, p in con.execute('SELECT id, path FROM documents WHERE code = ?', (code,)) if i not in seen]
        sheets, circuits = [], []
        for doc_id, path in docs:
            own = path.startswith(rel + '/')
            pages = con.execute('SELECT p.page, COALESCE(s.text, p.text) FROM pages p LEFT JOIN pages_spell s '
                                'ON s.doc_id = p.doc_id AND s.page = p.page WHERE p.doc_id = ? ORDER BY p.page', (doc_id,)).fetchall()
            pages = [(pg, t) for pg, t in pages if t]
            for pg, t in pages:
                if TD.search(t) or re.search(r'^\W*TECHNICAL\s+DA', t, re.M | re.I):
                    title, specs = parse_sheet(t)
                    if specs:
                        q = quality(' '.join(x['text'] for x in specs))
                        sheets.append((names_code(title, code), own, round(len(specs) * q, 1), path, pg, title, specs, q))
            secs, used, words, q = parse_circuit(pages)
            if secs:
                circuits.append((own, round(q, 2) * min(words, 400), path, used, secs, q))
        src = lambda path: os.path.relpath(os.path.join(Y2026, path), d).replace(os.sep, '/') if path.startswith(rel + '/') else path
        spec_f, circ_f = os.path.join(d, 'Specifications.json'), os.path.join(d, 'CircuitDescription.json')
        if sheets:
            sheets.sort(key=lambda s: (s[0], s[1], s[2]), reverse=True)
            best = sheets[0]
            doc = {'module': code, 'title': best[5], 'source': {'file': src(best[3]), 'page': best[4]}, 'ocr_quality': round(best[7], 2),
                   'read': 'OCR of the technical data sheet; usual OCR slips put right, the rest as read: check against the page',
                   'specifications': best[6]}
            also = [{'file': src(s[3]), 'page': s[4]} for s in sheets[1:] if s[0]]
            if also:
                doc['also_in'] = also[:12]
            open(spec_f, 'w', encoding='utf-8').write(json.dumps(doc, ensure_ascii=False, indent=1) + '\n')
            n_spec += 1
        if circuits:
            circuits.sort(key=lambda c: (c[0], c[1]), reverse=True)
            own, _, path, used, secs, q = circuits[0]
            doc = {'module': code, 'source': {'file': src(path), 'pages': used}, 'ocr_quality': round(q, 2),
                   'read': 'OCR of the manual\'s circuit description; check against the pages', 'sections': secs}
            open(circ_f, 'w', encoding='utf-8').write(json.dumps(doc, ensure_ascii=False, indent=1) + '\n')
            n_circ += 1
    print(f'{len(dirs)} modules: {n_spec} Specifications.json, {n_circ} CircuitDescription.json')


if __name__ == '__main__':
    main()
