"""PCB / EDA / mechanical-CAD extractor for the WBS - DATA SHUFFLER sidecars.

Detects by content (extensions in this archive are ambiguous), then pulls the
meaningful design content rather than raw dumps:

  Altium Designer   SchDoc / SchLib / PcbDoc / PcbLib (OLE), ASCII SchDoc,
                    PrjPcb, PrjPcbStructure, OutJob, *Preview thumbnails,
                    LDP / RUL / APR / DRR / annotation text reports
  P-CAD / ACCEL     binary .pcb/.sch/.p01/.s01 (best-effort strings),
                    ACCEL_ASCII .pcb/.sch/.net, pick-and-place, BOM
  Tango / Protel    Tango-PCB ASCII, Tango/Protel [ ] ( ) netlists
  OrCAD Capture     .dsn (OLE) best-effort parts / labels
  CAM               Gerber RS-274-D/X, Excellon NC drill, IPC-D-356 netlist,
                    Altium EIA binary drill, CAM350/Autoview job files
  Mechanical        DXF (text, layers, extents), DWG (version + recovered
                    strings), DWF, STEP header, HPGL plot labels
  Artwork           CorelDRAW .cdr (version + text objects)
  Misc look-alikes  ICCAVR .dp2 dependency lists, Xilinx .asy symbols and
                    XML schematics, Altera SignalTap .stp, XMOS .xn ...
"""
import os, re, struct, zlib, collections, io, csv, configparser

import core

EXTS = {'schdoc', 'pcbdoc', 'prjpcb', 'prjpcbstructure', 'schlib', 'pcblib', 'intlib', 'outjob',
        'schdocpreview', 'pcbdocpreview', 'vhdpreview', 'vpreview', 'ldppreview', 'asmpreview',
        'netpreview', 'annotationpreview', 'annotation', 'pcb', 'sch', 'dsn', 'brd', 'lbr', 'net',
        'pnp', 'bom', 'drl', 'drr', 'txt_drl', 'cam', 'gtl', 'gbl', 'gto', 'gbo', 'gts', 'gbs', 'gtp',
        'gbp', 'gko', 'gm1', 'gm3', 'gm4', 'gm6', 'g1', 'g2', 'g3', 'gp1', 'gp2', 'gp3', 'gpt', 'gpb',
        'gd1', 'gg1', 'gnd', 'gnd1', 'gnd2', 'gbr', 'ger', 'art', 'pho', 'top', 'bot', 'asy', 'pwr',
        'in1', 'in2', 'ipc', 'p01', 'p02', 'p03', 'p04', 'p05', 'p10', 's01', 's02', 's03', 'dwg',
        'dxf', 'dwf', 'stp', 'step', 'igs', 'iges', 'cdr', 'dp2', 'plt', 'sxr', 'ldp', 'schlog',
        'schcmd', 'schbak', 'pcbbak', 'ddb', 'apr', 'rul', 'ppf_eda', 'xn'}

MAXREAD = 40_000_000          # cap for any whole-file read
MAXPAR = 6000                 # cap on emitted paragraphs per file

REFDES = re.compile(r'^(?:[A-Z]{1,4}|[A-Z]+_)\d{1,4}[A-Z]?$')

# ---------------------------------------------------------------- helpers

def _read(path, n=MAXREAD):
    with open(path, 'rb') as f:
        return f.read(n)


def _dec(b):
    for enc in ('utf-8', 'cp1252'):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode('latin-1', 'replace')


def _textish(b):
    if not b:
        return True
    chunk = b[:8192]
    if b'\x00' in chunk:
        return False
    ctrl = sum(1 for c in chunk if c < 9 or (13 < c < 32))
    return ctrl / len(chunk) < 0.05


def _uniq(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x); out.append(x)
    return out


def _natkey(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', str(s))]


def _fmt(v, nd=3):
    try:
        v = float(v)
    except Exception:
        return str(v)
    s = f'{v:.{nd}f}'.rstrip('0').rstrip('.')
    return s or '0'


def _join(items, n=60):
    items = list(items)
    s = ', '.join(str(i) for i in items[:n])
    if len(items) > n:
        s += f' … (+{len(items) - n} more)'
    return s


def _strings(data, n=3):
    return [m.group().decode('latin-1') for m in re.finditer(rb'[\x20-\x7e]{%d,}' % n, data)]


JUNK_RE = re.compile(r'^[\W_]*$')


def _wordy(s, minlen=4):
    """Heuristic: does a recovered binary string look like human text/identifier?"""
    s = s.strip()
    if len(s) < minlen or len(s) > 300:
        return False
    if re.search(r'(.)\1{3,}', s):
        return False
    letters = sum(c.isalpha() for c in s)
    if letters < 2 or letters / len(s) < 0.5:
        return False
    if not re.search(r'[A-Za-z]{2}', s):
        return False
    if not re.search(r'[AEIOUYaeiouy0-9 ]', s):
        return False
    # random binary often mixes case wildly
    if len(s) <= 8 and re.search(r'[a-z][A-Z][a-z]', s) and ' ' not in s:
        return False
    if sum(c in '{}[]<>\\^`|~@$%&*#' for c in s) > max(1, len(s) // 8):
        return False
    return True


def _kv_pipe(text):
    """Altium '|KEY=VAL|KEY=VAL' record -> dict (upper keys; %UTF8% variants preferred)."""
    d = {}
    for part in text.split('|'):
        if '=' not in part:
            continue
        k, v = part.split('=', 1)
        k = k.strip().upper()
        if k.startswith('%UTF8%'):
            k = k[6:]
            try:
                v = v.encode('latin-1').decode('utf-8')
            except Exception:
                pass
            d[k] = v
        else:
            d.setdefault(k, v)
    return d


def _mil(v):
    """'1000mil' / '2.54mm' / '1000' -> float mils."""
    if v is None:
        return None
    m = re.match(r'\s*(-?[\d.]+(?:[Ee][-+]?\d+)?)\s*(mil|mm|in)?', str(v))
    if not m:
        return None
    x = float(m.group(1))
    u = (m.group(2) or 'mil').lower()
    return x / 0.0254 if u == 'mm' else x * 1000 if u == 'in' else x


def _size_str(w_mil, h_mil):
    return f'{_fmt(w_mil / 1000)} x {_fmt(h_mil / 1000)} in ({_fmt(w_mil * 0.0254, 1)} x {_fmt(h_mil * 0.0254, 1)} mm)'


def _result(kind='data', **kw):
    r = {'kind': kind}
    r.update({k: v for k, v in kw.items() if v})
    if 'paragraphs' in r and len(r['paragraphs']) > MAXPAR:
        n = len(r['paragraphs'])
        r['paragraphs'] = r['paragraphs'][:MAXPAR]
        r.setdefault('notes', []).append(f'Listing truncated to {MAXPAR:,} of {n:,} entries.')
    return r


def _generic_text(path, typ='Text file', data=None):
    if data is None:
        data = _read(path, 20_000_000)
    text = _dec(data)
    pars = core.split_paragraphs(text)
    return _result('document', type=typ, paragraphs=pars)


def _binary_note(path, typ, data=None, note=None, strings=True):
    data = data if data is not None else _read(path, 8_000_000)
    pars = []
    if strings:
        ss = _uniq(s.strip() for s in _strings(data, 5) if _wordy(s, 5))
        if ss:
            pars = [{'heading': 'Readable strings (best effort)'}, '\n'.join(ss[:400])]
    notes = [note] if note else []
    if not pars:
        notes.append('Binary file: no readable text recovered.')
    summary = (f'{typ}: {len(ss)} readable strings recovered, e.g. ' + _join([x[:40] for x in ss], 10) + '.') if pars else ''
    return _result('binary', type=typ, paragraphs=pars, notes=notes, summary=summary,
                   meta=[('First bytes', '`' + data[:16].hex(' ') + '`')])

# ---------------------------------------------------------------- Altium OLE

def _ole(path):
    import olefile
    return olefile.OleFileIO(path)


def _altium_sch_records(data):
    """Altium schematic binary stream -> list of dicts (header first). Binary records -> {'__bin': type}."""
    out, pos, n = [], 0, len(data)
    while pos + 4 <= n:
        ln = data[pos] | (data[pos + 1] << 8) | (data[pos + 2] << 16)
        typ = data[pos + 3]
        rec = data[pos + 4:pos + 4 + ln]
        pos += 4 + ln
        if typ == 0:
            out.append(_kv_pipe(rec.rstrip(b'\x00').decode('latin-1')))
        else:
            out.append({'__bin': typ, '__raw': rec})
        if ln == 0 and pos >= n:
            break
    return out


def _altium_pcb_records(data):
    """PcbDoc text streams: uint32 length + '|K=V...' records."""
    out, pos, n = [], 0, len(data)
    while pos + 4 <= n:
        ln = struct.unpack_from('<I', data, pos)[0]
        if ln <= 0 or pos + 4 + ln > n + 1:
            break
        out.append(_kv_pipe(data[pos + 4:pos + 4 + ln].rstrip(b'\x00').decode('latin-1')))
        pos += 4 + ln
    return out


TB_KEYS = ['Title', 'DocumentNumber', 'Revision', 'Date', 'DrawnBy', 'Author', 'CompanyName',
           'Organization', 'Engineer', 'CheckedBy', 'ApprovedBy', 'SheetNumber', 'SheetTotal',
           'DocumentName', 'ModifiedDate', 'Address1', 'Address2', 'Address3', 'Address4']


def _clean_alt_text(t):
    return (t or '').replace('~1', '\n').strip()


def _schdoc_from_records(recs, typ='Altium schematic (SchDoc)'):
    hdr = recs[0] if recs and 'RECORD' not in recs[0] else {}
    body = recs[1:] if hdr else recs
    comps = {}           # index -> dict
    order = []
    for i, r in enumerate(body):
        if r.get('RECORD') == '1':
            comps[i] = {'libref': r.get('LIBREFERENCE') or r.get('DESIGNITEMID', ''),
                        'desc': r.get('COMPONENTDESCRIPTION', ''), 'des': '', 'comment': '',
                        'value': '', 'fp': [], 'parts': r.get('PARTCOUNT', ''), 'params': {},
                        'lib': r.get('SOURCELIBRARYNAME') or r.get('LIBRARYPATH', '')}
            order.append(i)
    impl_owner = {}
    sheet_params, netlabels, power, ports, labels, notes, sheets, sheetfiles = {}, [], [], [], [], [], [], []
    pins = 0
    for i, r in enumerate(body):
        rt = r.get('RECORD')
        try:
            own = int(r.get('OWNERINDEX', '-1'))
        except ValueError:
            own = -1
        if rt == '34' and own in comps:
            comps[own]['des'] = r.get('TEXT', '')
        elif rt == '41':
            name, text = r.get('NAME', ''), r.get('TEXT', '')
            if own in comps:
                if name.lower() == 'comment':
                    comps[own]['comment'] = text
                elif name.lower() == 'value':
                    comps[own]['value'] = text
                elif text and text != '*' and not name.startswith('_'):
                    comps[own]['params'][name] = text
            elif own == -1 and name:
                if text and text != '*':
                    sheet_params[name] = text
        elif rt == '44' and own in comps:
            impl_owner[i] = own
        elif rt == '45':
            c = impl_owner.get(own)
            if c is not None and r.get('MODELTYPE', '').upper() == 'PCBLIB':
                mn = r.get('MODELNAME', '')
                if mn:
                    if r.get('ISCURRENT') == 'T':
                        comps[c]['fp'].insert(0, mn)
                    else:
                        comps[c]['fp'].append(mn)
        elif rt == '25':
            netlabels.append(r.get('TEXT', ''))
        elif rt == '17':
            power.append(r.get('TEXT', ''))
        elif rt == '18':
            ports.append(r.get('NAME', ''))
        elif rt == '4':
            labels.append(_clean_alt_text(r.get('TEXT', '')))
        elif rt in ('28', '209'):
            notes.append(_clean_alt_text(r.get('TEXT', '')))
        elif rt == '32':
            sheets.append(r.get('TEXT', ''))
        elif rt == '33':
            sheetfiles.append(r.get('TEXT', ''))
        elif rt == '2' or r.get('__bin') == 1:
            pins += 1
    # resolve '=Param' indirections (e.g. Comment '=Value')
    for c in comps.values():
        low = {k.lower(): v for k, v in c['params'].items()}
        low['value'] = c['value'] or low.get('value', '')
        if c['comment'].startswith('='):
            c['comment'] = low.get(c['comment'][1:].strip().lower(), '')
        if c['value'] == c['comment']:
            c['value'] = ''
        c['params'] = {k: v for k, v in c['params'].items() if 'Record=' not in v and k.lower() not in ('value',)}
    # multi-part components share a designator; merge by designator
    rows, seen = [], {}
    for i in order:
        c = comps[i]
        key = c['des'] or f'#{i}'
        if key in seen:
            continue
        seen[key] = 1
        rows.append(c)
    rows.sort(key=lambda c: _natkey(c['des']))
    tb = [(k, sheet_params[k]) for k in TB_KEYS if k in sheet_params]
    other_params = [(k, v) for k, v in sheet_params.items() if k not in TB_KEYS and 'Record=' not in v
                    and k not in ('CurrentTime', 'CurrentDate', 'Time', 'DocumentFullPathAndName', 'PageSetup')]
    title = sheet_params.get('Title', '')
    pars, outline, meta, kws = [], [], [], []
    if tb or other_params:
        pars.append({'heading': 'Title block'})
        pars.extend(f'{k}: {v}' for k, v in tb + other_params)
    if rows:
        pars.append({'heading': f'Components ({len(rows)})'})
        for c in rows:
            bits = [c['des'] or '(no designator)']
            if c['comment'] and c['comment'] != '*':
                bits.append(c['comment'])
            if c['value'] and c['value'] not in (c['comment'], '*'):
                bits.append('value ' + c['value'])
            if c['libref']:
                bits.append('lib ref ' + c['libref'])
            if c['fp']:
                bits.append('footprint ' + c['fp'][0])
            if c['desc']:
                bits.append(c['desc'])
            extra = [f'{k}={v}' for k, v in list(c['params'].items())[:6]]
            if extra:
                bits.append('; '.join(extra))
            pars.append(' — '.join(bits))
    nl = sorted(set(x for x in netlabels if x), key=_natkey)
    pw = sorted(set(x for x in power if x), key=_natkey)
    pt = sorted(set(x for x in ports if x), key=_natkey)
    if nl:
        pars.append({'heading': f'Net labels ({len(nl)})'}); pars.append(', '.join(nl))
    if pw:
        pars.append({'heading': 'Power ports'}); pars.append(', '.join(pw))
    if pt:
        pars.append({'heading': f'Ports ({len(pt)})'}); pars.append(', '.join(pt))
    if sheets or sheetfiles:
        pars.append({'heading': 'Sheet symbols'})
        for a, b in zip(sheets + [''] * len(sheetfiles), sheetfiles + [''] * len(sheets)):
            if a or b:
                pars.append(f'{a} → {b}' if b else a)
    txt = [t for t in labels + notes if t]
    if txt:
        pars.append({'heading': 'Text and notes'})
        pars.extend(_uniq(txt))
    fps = sorted(set(c['fp'][0] for c in rows if c['fp']), key=_natkey)
    librefs = sorted(set(c['libref'] for c in rows if c['libref']), key=_natkey)
    meta.append(('Components', len(rows)))
    if pins:
        meta.append(('Pins', pins))
    meta.append(('Net labels', len(nl)))
    if pt:
        meta.append(('Ports', len(pt)))
    if hdr.get('HEADER'):
        meta.append(('Format', hdr['HEADER']))
    for k, v in tb[:8]:
        meta.append((k, v))
    if fps:
        meta.append(('Footprints used', _join(fps, 40)))
    vals = [c['comment'] or c['value'] for c in rows if (c['comment'] or c['value']) not in ('', '*')]
    pns = []
    for c in rows:
        for k, v in c['params'].items():
            if re.search(r'(?i)part ?(number|no)|\bP/?N\b|mfr|manufacturer.*pn', k) and v.strip():
                pns.append(v.strip())
    kws = [x for x in (title, sheet_params.get('Title1', ''), sheet_params.get('Title2', '')) if x]
    kws += [x for x in sheet_params.get('DocumentNumber', '').split() if x]
    kws += [v for v, _ in collections.Counter(vals).most_common(8)]
    kws += [v for v, _ in collections.Counter(pns).most_common(8)]
    kws += nl[:4] + pt[:4] + fps[:5] + librefs[:5]
    if pns:
        meta.append(('Part numbers', _join(sorted(set(pns), key=_natkey), 60)))
    s = f'{typ}' + (f' "{title}"' if title else '') + f': {len(rows)} components'
    if nl:
        s += f', {len(nl)} net labels'
    if pt:
        s += f', {len(pt)} ports'
    s += '.'
    if librefs:
        s += ' Parts include ' + _join(_uniq(vals)[:12] or librefs[:12], 12) + '.'
    if txt and len(rows) < 3:
        s += ' Text: ' + _join([t.replace('\n', ' ')[:60] for t in _uniq(txt)], 15) + '.'
    nln = [n for n in nl if not re.match(r'^(NET|N)\d+$', n, re.I)]
    if nln:
        s += ' Nets: ' + _join(nln, 15) + '.'
    if pt:
        s += ' Ports: ' + _join(pt, 15) + '.'
    return _result(type=typ, title=title, meta=meta, summary=s, keywords=kws, paragraphs=pars)


def altium_schdoc(path, data):
    o = _ole(path)
    try:
        if not o.exists('FileHeader'):
            return _ole_generic(path, o, 'Altium schematic (unrecognised OLE layout)')
        recs = _altium_sch_records(o.openstream('FileHeader').read())
    finally:
        o.close()
    return _schdoc_from_records(recs)


def altium_schdoc_ascii(path, data):
    text = _dec(data)
    recs = []
    for line in text.splitlines():
        if line.startswith('|'):
            recs.append(_kv_pipe(line))
    return _schdoc_from_records(recs, 'Altium schematic (ASCII SchDoc)')


def altium_schlib(path, data):
    o = _ole(path)
    try:
        hdr = _altium_sch_records(o.openstream('FileHeader').read()) if o.exists('FileHeader') else [{}]
        h = hdr[0] if hdr else {}
        n = int(h.get('COMPCOUNT', '0') or 0)
        comps = []
        for i in range(n):
            comps.append([h.get(f'LIBREF{i}', ''), h.get(f'COMPDESCR{i}', ''), h.get(f'PARTCOUNT{i}', '')])
        names = {c[0] for c in comps}
        dirs = sorted({e[0] for e in o.listdir() if len(e) > 1})
        details = {}
        for d in dirs:
            if not o.exists(d + '/Data'):
                continue
            recs = _altium_sch_records(o.openstream(d + '/Data').read(4_000_000))
            pins, fps, params = [], [], {}
            for r in recs:
                rt = r.get('RECORD')
                if rt == '2':
                    pins.append((r.get('DESIGNATOR', ''), r.get('NAME', '')))
                elif r.get('__bin') == 1:
                    raw = r['__raw']
                    ss = re.findall(rb'[\x20-\x7e]{1,}', raw[20:])
                    pins.append(('', ''))
                elif rt == '45' and r.get('MODELTYPE', '').upper() == 'PCBLIB':
                    fps.append(r.get('MODELNAME', ''))
                elif rt == '41' and r.get('NAME') and r.get('TEXT') not in (None, '', '*'):
                    params[r['NAME']] = r['TEXT']
            details[d] = (pins, fps, params)
            if d not in names:
                comps.append([d, '', ''])
    finally:
        o.close()
    pars = [{'heading': f'Library components ({len(comps)})'}]
    for name, desc, pc in comps:
        pins, fps, params = details.get(name, details.get(name[:31], ([], [], {})))
        bits = [name]
        if desc:
            bits.append(desc)
        if pins:
            bits.append(f'{len(pins)} pins')
        if fps:
            bits.append('footprint ' + ', '.join(_uniq(fps)))
        if params:
            bits.append('; '.join(f'{k}={v}' for k, v in list(params.items())[:6]))
        pars.append(' — '.join(bits))
        named = [f'{d}:{nm}' for d, nm in pins if d or nm]
        if named:
            pars.append(f'{name} pins: ' + _join(named, 200))
    s = f'Altium schematic library with {len(comps)} component symbols: ' + _join([c[0] for c in comps], 25) + '.'
    return _result(type='Altium schematic library (SchLib)', summary=s, paragraphs=pars,
                   keywords=[c[0] for c in comps[:10]], meta=[('Components', len(comps))])


def _layer_stack(b):
    names = {}
    for k, v in b.items():
        m = re.match(r'LAYER(\d+)NAME$', k)
        if m:
            names[int(m.group(1))] = v
    stack = []
    if names:
        cur, seen = 1, set()
        while cur and cur not in seen and cur in names:
            seen.add(cur)
            cu = b.get(f'LAYER{cur}COPTHICK', '')
            dh = b.get(f'LAYER{cur}DIELHEIGHT', '')
            dm = b.get(f'LAYER{cur}DIELMATERIAL', '')
            entry = names[cur] + (f' (Cu {cu}' + (f', dielectric {dh} {dm}'.rstrip() if dh and cur != 32 else '') + ')' if cu else '')
            stack.append(entry)
            try:
                cur = int(b.get(f'LAYER{cur}NEXT', '0'))
            except ValueError:
                break
    v9 = []
    i = 0
    while f'V9_STACK_LAYER{i}_NAME' in b:
        v9.append(b[f'V9_STACK_LAYER{i}_NAME'])
        i += 1
    mech = [names[n] for n in sorted(names) if b.get(f'LAYER{n}MECHENABLED') == 'TRUE']
    return stack, v9, mech


def altium_pcbdoc(path, data):
    o = _ole(path)
    try:
        def rd(n, cap=20_000_000):
            return o.openstream(n).read(cap) if o.exists(n) else b''
        fh = rd('FileHeader')
        fmt = _dec(fh[5:]).strip('\x00 ') if fh else ''
        board = {}
        for r in _altium_pcb_records(rd('Board6/Data')):
            for k, v in r.items():
                board.setdefault(k, v)
        comps = _altium_pcb_records(rd('Components6/Data'))
        nets = [r.get('NAME', '') for r in _altium_pcb_records(rd('Nets6/Data'))]
        classes = _altium_pcb_records(rd('Classes6/Data'))
        rules = _altium_pcb_records(rd('Rules6/Data'))
        # texts: comment strings per component
        comments, free_text = {}, []
        t6 = rd('Texts6/Data')
        pos = 0
        while pos + 5 < len(t6):
            if t6[pos] != 5:
                break
            ln = struct.unpack_from('<I', t6, pos + 1)[0]
            sub = t6[pos + 5:pos + 5 + ln]
            pos += 5 + ln
            if pos + 4 > len(t6):
                break
            ln2 = struct.unpack_from('<I', t6, pos)[0]
            s2 = t6[pos + 4:pos + 4 + ln2]
            pos += 4 + ln2
            txt = _dec(s2[1:1 + s2[0]]) if s2 else ''
            if len(sub) > 42:
                comp = struct.unpack_from('<H', sub, 7)[0]
                is_comment, is_des = sub[40], sub[41]
                if comp != 0xFFFF:
                    if is_comment and not is_des and txt.strip() not in ('Comment', '.Comment', '*'):
                        comments[comp] = txt
                elif txt.strip():
                    free_text.append(txt.strip())
        pads = o.get_size('Pads6/Data') if o.exists('Pads6/Data') else 0
    finally:
        o.close()
    stack, v9, mech = _layer_stack(board)
    xs = [_mil(board[k]) for k in board if re.match(r'VX\d+$', k)]
    ys = [_mil(board[k]) for k in board if re.match(r'VY\d+$', k)]
    xs = [x for x in xs if x is not None]; ys = [y for y in ys if y is not None]
    size = None
    if len(xs) >= 3 and len(ys) >= 3 and max(xs) > min(xs):
        size = (max(xs) - min(xs), max(ys) - min(ys))
    rows = []
    for i, c in enumerate(comps):
        rows.append({'des': c.get('SOURCEDESIGNATOR', '') or c.get('NAME', ''),
                     'fp': c.get('PATTERN', ''), 'libref': c.get('SOURCELIBREFERENCE', ''),
                     'desc': c.get('SOURCEDESCRIPTION', ''), 'layer': c.get('LAYER', ''),
                     'comment': comments.get(i, ''), 'x': c.get('X', ''), 'y': c.get('Y', ''),
                     'rot': c.get('ROTATION', '')})
    rows.sort(key=lambda r: _natkey(r['des']))
    pars, meta = [], []
    pars.append({'heading': 'Board'})
    if board.get('FILENAME'):
        pars.append('Saved as: ' + board['FILENAME'])
    if board.get('DATE'):
        pars.append(f"Saved: {board.get('DATE')} {board.get('TIME', '')}".strip())
    if size:
        pars.append('Board outline: ' + _size_str(*size))
    if stack:
        pars.append({'heading': f'Layer stack ({len(stack)} copper layers)'})
        pars.extend(stack)
    elif v9:
        pars.append({'heading': 'Layer stack'})
        pars.extend(v9)
    if mech:
        pars.append('Mechanical layers enabled: ' + ', '.join(mech))
    if rows:
        pars.append({'heading': f'Components ({len(rows)})'})
        for r in rows:
            bits = [r['des'] or '?']
            if r['comment']:
                bits.append(r['comment'])
            if r['fp']:
                bits.append('footprint ' + r['fp'])
            if r['libref'] and r['libref'] != r['fp']:
                bits.append('lib ref ' + r['libref'])
            if r['desc'] and r['desc'] not in (r['libref'], r['fp']):
                bits.append(r['desc'])
            loc = f"{r['layer'].lower()} @ {r['x']},{r['y']}"
            try:
                rot = float(r['rot'])
                if rot:
                    loc += f' rot {_fmt(rot, 1)}'
            except Exception:
                pass
            bits.append(loc)
            pars.append(' — '.join(bits))
    nn = sorted(set(n for n in nets if n), key=_natkey)
    named = [n for n in nn if not re.match(r'^Net[A-Z]+\d+_\d+$|^NET\d+$|^N\d+$', n)]
    if nn:
        pars.append({'heading': f'Nets ({len(nn)})'})
        pars.append(', '.join(nn))
    cls = [r.get('NAME', '') for r in classes if r.get('SUPERCLASS') == 'FALSE' and r.get('NAME')]
    if cls:
        pars.append({'heading': 'Classes'}); pars.append(', '.join(cls))
    rl = [f"{r.get('RULEKIND', '')}: {r.get('NAME', '')}" for r in rules if r.get('NAME')]
    if rl:
        pars.append({'heading': f'Design rules ({len(rl)})'}); pars.append('; '.join(rl[:200]))
    ft = _uniq(t for t in free_text if t)
    if ft:
        pars.append({'heading': 'Board text'}); pars.extend(ft[:500])
    meta.append(('Format', fmt or 'Altium PCB binary'))
    meta.append(('Components', len(rows)))
    meta.append(('Nets', len(nn)))
    if stack:
        meta.append(('Copper layers', len(stack)))
    if size:
        meta.append(('Board size', _size_str(*size)))
    if board.get('DATE'):
        meta.append(('Saved', f"{board.get('DATE')} {board.get('TIME', '')}"))
    fps = sorted(set(r['fp'] for r in rows if r['fp']), key=_natkey)
    if fps:
        meta.append(('Footprints', _join(fps, 40)))
    vals = [r['comment'] for r in rows if r['comment']]
    s = f'Altium PCB layout: {len(rows)} components, {len(nn)} nets'
    if stack:
        s += f', {len(stack)}-layer board'
    if size:
        s += ', ' + _size_str(*size)
    s += '.'
    if vals:
        s += ' Parts include ' + _join(_uniq(vals), 12) + '.'
    if named:
        s += ' Named nets: ' + _join(named, 15) + '.'
    kws = [v for v, _ in collections.Counter(vals).most_common(8)] + named[:5] + fps[:6] + nn[:6]
    return _result(type='Altium PCB layout (PcbDoc)', meta=meta, summary=s, keywords=kws, paragraphs=pars)


def altium_pcblib(path, data):
    o = _ole(path)
    try:
        skip = {'FileHeader', 'FileVersionInfo', 'Library', 'Textures', 'Models', 'ModelsNoEmbed',
                'ComponentParamsTOC', 'LayerKindMapping', 'SectionKeys', 'PadViaLibrary', 'EmbeddedFonts'}
        fps = []
        for d in sorted({e[0] for e in o.listdir() if len(e) > 1}):
            if d in skip:
                continue
            params = {}
            if o.exists(d + '/Parameters'):
                pr = o.openstream(d + '/Parameters').read(100000)
                params = _kv_pipe(pr[4:].rstrip(b'\x00').decode('latin-1'))
            fps.append((params.get('PATTERN', d), params.get('DESCRIPTION', ''), params.get('HEIGHT', '')))
        fh = o.openstream('FileHeader').read() if o.exists('FileHeader') else b''
    finally:
        o.close()
    pars = [{'heading': f'Footprints ({len(fps)})'}]
    for n, d, h in fps:
        pars.append(' — '.join(x for x in (n, d, ('height ' + h) if h and h not in ('0mil',) else '') if x))
    s = f'Altium PCB footprint library with {len(fps)} footprints: ' + _join([f[0] for f in fps], 25) + '.'
    return _result(type='Altium PCB footprint library (PcbLib)', summary=s, paragraphs=pars,
                   keywords=[f[0] for f in fps[:10]],
                   meta=[('Footprints', len(fps)), ('Format', _dec(fh[5:]).strip('\x00 '))])


def _ole_generic(path, o, typ):
    pars = [{'heading': 'OLE streams'}]
    rows = []
    for e in o.listdir():
        n = '/'.join(e)
        rows.append(f'{n} ({o.get_size(n):,} bytes)')
    pars.append('\n'.join(rows[:300]))
    return _result('binary', type=typ, paragraphs=pars, meta=[('Streams', len(rows))])


def altium_intlib(path, data):
    o = _ole(path)
    try:
        r = _ole_generic(path, o, 'Altium integrated library (IntLib)')
    finally:
        o.close()
    return r


def orcad_dsn(path, data):
    o = _ole(path)
    try:
        pages, lib = [], b''
        for e in o.listdir():
            n = '/'.join(e)
            if 'Pages/' in n:
                pages.append((n.split('/')[-1], o.openstream(n).read(8_000_000)))
            elif n in ('Library', 'Cache'):
                lib += o.openstream(n).read(4_000_000)
    finally:
        o.close()
    pars, comps, labels = [], {}, []
    fields = {}
    ls = _strings(lib, 2)
    tb_names = ['Title', 'Doc', 'RevCode', 'OrgName', 'OrgAddr1', 'OrgAddr2', 'Page Create Date', 'Page Modify Date']
    olbs = sorted(set(s for s in ls if s.upper().endswith('.OLB')))
    for pname, pd in pages:
        ss = [s for s in _strings(pd, 2)]
        for i, s in enumerate(ss):
            if s.endswith('.Normal') and i + 1 < len(ss):
                part = s[:-7]
                for j in range(i + 1, min(i + 4, len(ss))):
                    if REFDES.match(ss[j]) or re.match(r'^[A-Z]{1,3}\?$', ss[j]):
                        comps.setdefault(ss[j] + ('' if not ss[j].endswith('?') else f'#{i}'), (part, pname))
                        break
        for s in ss:
            if len(s) >= 2 and re.match(r'^[A-Za-z+\-/][A-Za-z0-9_+\-/\\\.]*$', s) and not s.endswith('.Normal') \
                    and _wordy(s, 2) is not False and not REFDES.match(s) and s not in ('PAGE1', 'TitleBlock0'):
                labels.append(s)
    partnames = {p for p, _ in comps.values()}
    labels = [l for l in _uniq(labels) if l not in partnames and len(l) >= 2 and re.search(r'[A-Za-z]', l)
              and not re.search(r'[a-z][A-Z]', l) and sum(c.isalpha() for c in l) >= 2]
    rows = sorted(comps.items(), key=lambda kv: _natkey(kv[0]))
    pars.append({'heading': f'Parts placed ({len(rows)})'})
    for ref, (part, pg) in rows:
        pars.append(f"{ref.split('#')[0]} — {part} ({pg})")
    if labels:
        pars.append({'heading': 'Net / port labels and text (best effort)'})
        pars.append(', '.join(labels[:600]))
    if olbs:
        pars.append({'heading': 'Libraries'}); pars.append('\n'.join(olbs))
    parts = _uniq(p for p, _ in comps.values())
    s = (f'OrCAD Capture schematic design with {len(pages)} page(s) and {len(rows)} placed parts'
         + (': ' + _join(parts, 15) if parts else '') + '.')
    return _result(type='OrCAD Capture schematic (DSN)', summary=s, paragraphs=pars, keywords=parts[:10],
                   meta=[('Pages', ', '.join(p for p, _ in pages)), ('Parts', len(rows))],
                   notes=['OrCAD binary format: parts and labels recovered heuristically from strings.'])

# ---------------------------------------------------------------- Altium text files

def _ini(text):
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    try:
        cp.read_string(text)
    except Exception:
        # tolerate duplicate / malformed lines
        cleaned = '\n'.join(l for l in text.splitlines() if l.startswith('[') or '=' in l)
        cp = configparser.RawConfigParser(strict=False, interpolation=None)
        cp.optionxform = str
        try:
            cp.read_string(cleaned)
        except Exception:
            return None
    return cp


def altium_prjpcb(path, data):
    text = _dec(data)
    cp = _ini(text)
    if cp is None:
        return _generic_text(path, 'Altium PCB project', data)
    docs, variants, params, outs = [], [], [], []
    for sec in cp.sections():
        if sec.startswith('Document') or sec.startswith('GeneratedDocument'):
            p = cp.get(sec, 'DocumentPath', fallback='')
            if p:
                docs.append(p + (' (generated)' if sec.startswith('Generated') else ''))
        elif sec.startswith('ProjectVariant'):
            variants.append(cp.get(sec, 'Description', fallback=sec))
        elif sec.startswith('Parameter'):
            params.append(f"{cp.get(sec, 'Name', fallback='')} = {cp.get(sec, 'Value', fallback='')}")
        elif sec.startswith('OutputGroup'):
            nm = cp.get(sec, 'Name', fallback=sec)
            items = []
            for k, v in cp.items(sec):
                m = re.match(r'OutputType(\d+)$', k)
                if m:
                    on = cp.get(sec, f'OutputName{m.group(1)}', fallback='')
                    items.append(f'{v}' + (f' ({on})' if on and on != v else ''))
            outs.append(f'{nm}: ' + (', '.join(items) if items else '(none)'))
    design = dict(cp.items('Design')) if cp.has_section('Design') else {}
    pars = []
    if docs:
        pars.append({'heading': f'Documents ({len(docs)})'}); pars.extend(docs)
    if variants:
        pars.append({'heading': 'Variants'}); pars.extend(variants)
    if params:
        pars.append({'heading': 'Project parameters'}); pars.extend(params)
    if outs:
        pars.append({'heading': 'Output groups'}); pars.extend(outs)
    sch = [d for d in docs if d.lower().endswith('.schdoc')]
    pcb = [d for d in docs if d.lower().endswith('.pcbdoc')]
    s = f'Altium Designer PCB project with {len(docs)} documents ({len(sch)} schematic sheets, {len(pcb)} PCB)'
    s += (': ' + _join([os.path.basename(d.replace('\\', '/')) for d in docs], 12)) if docs else ''
    s += '.'
    meta = [('Documents', len(docs))]
    if design.get('OutputPath'):
        meta.append(('Output path', design['OutputPath']))
    if variants:
        meta.append(('Variants', ', '.join(variants)))
    return _result(type='Altium PCB project (PrjPcb)', summary=s, paragraphs=pars, meta=meta,
                   keywords=[os.path.splitext(os.path.basename(d.replace('\\', '/')))[0] for d in docs[:8]])


def altium_structure(path, data):
    text = _dec(data)
    pars = []
    for line in text.splitlines():
        if not line.strip():
            continue
        d = _kv_pipe('|' + line)
        rec = d.pop('RECORD', '')
        pars.append(f'{rec}: ' + ', '.join(f'{k.title()}={v}' for k, v in d.items() if v))
    top = re.findall(r'FileName=([^|\r\n]+)', text)
    s = 'Altium project hierarchy (compiled sheet structure)' + (': top-level ' + top[0] if top else '') + '.'
    return _result(type='Altium project structure (PrjPcbStructure)', summary=s, paragraphs=pars)


def altium_outjob(path, data):
    text = _dec(data)
    cp = _ini(text)
    if cp is None:
        return _generic_text(path, 'Altium output job', data)
    pars, n_en, n_all = [], 0, 0
    for sec in cp.sections():
        if not sec.startswith('OutputGroup'):
            continue
        pars.append({'heading': cp.get(sec, 'Name', fallback=sec)})
        media = [v for k, v in cp.items(sec) if re.match(r'OutputMedium\d+$', k)]
        if media:
            pars.append('Output media: ' + ', '.join(media))
        for k, v in cp.items(sec):
            m = re.match(r'OutputType(\d+)$', k)
            if m:
                i = m.group(1)
                en = cp.get(sec, f'OutputEnabled{i}', fallback='0') == '1' or any(
                    cp.get(sec, f'OutputEnabled{i}_OutputMedium{j}', fallback='0') == '1' for j in range(1, 10))
                n_all += 1; n_en += en
                doc = cp.get(sec, f'OutputDocumentPath{i}', fallback='')
                pars.append(f"{v}: {cp.get(sec, f'OutputName{i}', fallback='')}"
                            + (f' [{doc}]' if doc else '') + (' (enabled)' if en else ''))
    s = f'Altium output job defining {n_all} outputs ({n_en} enabled).'
    return _result(type='Altium output job (OutJob)', summary=s, paragraphs=pars)


def altium_preview(path, data):
    text = _dec(data[:20000])
    kv = dict(re.findall(r'^(\w+(?:Width|Height|OriginalSize))=(\d+)', text, re.M))
    src = os.path.basename(path)
    src = re.sub(r'(?i)preview$', '', src)
    sizes = []
    for k in ('Large', 'Medium', 'Small'):
        if f'{k}ImageWidth' in kv:
            sizes.append(f"{k.lower()} {kv[f'{k}ImageWidth']}x{kv.get(f'{k}ImageHeight', '?')}")
    s = (f'Altium Designer preview thumbnail cache for {src} (zlib-compressed bitmap images: '
         + (', '.join(sizes) or 'unknown sizes') + '). No textual design content.')
    return _result('binary', type='Altium document preview thumbnail', summary=s,
                   meta=[('Preview of', src), ('Images', ', '.join(sizes))])


def altium_pipe_report(path, data, typ):
    text = _dec(data)
    lines = [l for l in text.splitlines() if l.strip()]
    pars = []
    for l in lines:
        if '|' in l and '=' in l:
            pars.append(', '.join(f'{k}={v}' for k, v in (p.split('=', 1) for p in l.split('|') if '=' in p)))
        else:
            pars.append(l)
    first = lines[0] if lines else ''
    s = f'{typ}' + (f' — {first}' if first else '') + f' ({max(0, len(lines) - 1)} entries).'
    return _result(type=typ, summary=s, paragraphs=pars)


def aperture_report(path, data):
    text = _dec(data)
    rows = [l.split() for l in text.splitlines() if re.match(r'\s*D\d+\s', l)]
    shapes = collections.Counter(r[1] for r in rows if len(r) > 1)
    pars = [l.strip() for l in text.splitlines() if l.strip()]
    s = (f'Gerber aperture list with {len(rows)} D-codes'
         + (' (' + ', '.join(f'{v} {k.lower()}' for k, v in shapes.most_common()) + ')' if shapes else '') + '.')
    return _result(type='Gerber aperture table', summary=s, paragraphs=pars, meta=[('Apertures', len(rows))])

# ---------------------------------------------------------------- P-CAD / ACCEL

PCAD_FIELDS = ['Title', 'Drawing Number', 'DRAWING NUMBER 2', 'Revision', 'Date', 'Author', 'Drawn By',
               'Company Name', 'Engineer', 'Checked By', 'Approved By']
PCAD_FIELDSET = set(PCAD_FIELDS) | {'Current Date', 'Current Time', 'Filename', 'Sheet Number',
                                     'Number Of Sheets', 'Modified Date', 'Time'}
PCAD_JUNK = {'QUALITY', 'Quality', 'Default text style', 'Part Attribute style', 'Pin Attribute style',
             'Wire Attribute style', 'Port Name style', 'Default pad style', 'Default via style',
             'True type font text styl', 'williemadeusdoit', 'PadToPadClearance', 'PadToLineClearance',
             'LineToLineClearance', 'ViaToPadClearance', 'ViaToLineClearance', 'ViaToViaClearance',
             'Value', 'RefDes', 'Type', 'Binary', 'OLD_LICENSE_INFORMATION'}


def pcad_binary(path, data):
    head = _dec(data[:200])
    ver = ''
    m = re.search(r';([^\r\n;]+?V[\d.]+)', head)
    if m:
        ver = m.group(1).strip()
    is_sch = 'Schematic' in head
    ss = [m.group().decode('cp1252') for m in re.finditer(rb'[\x20-\x7e]{2,}', data)]
    libs = sorted(set(s for s in ss if s.upper().endswith('.LIB')), key=str.lower)
    comps = collections.OrderedDict()
    # schematic: <lib>.LIB <part type> <refdes> ... Value <value>
    for i, s in enumerate(ss):
        if s.upper().endswith('.LIB') and i + 2 < len(ss):
            typ, ref = ss[i + 1], ss[i + 2]
            if REFDES.match(ref) and is_sch:
                val = ''
                for j in range(i + 3, min(i + 120, len(ss))):
                    if ss[j].upper().endswith('.LIB'):
                        break
                    if ss[j] == 'Value' and j + 1 < len(ss):
                        val = ss[j + 1]; break
                comps.setdefault(ref, {'type': typ, 'value': val, 'pattern': ''})
        if s == 'RefDes' and i + 1 < len(ss) and REFDES.match(ss[i + 1]):
            ref = ss[i + 1]
            c = comps.setdefault(ref, {'type': '', 'value': '', 'pattern': ''})
            for k in range(i - 1, max(i - 7, -1), -1):
                if ss[k] == 'Value' and k + 1 < i:
                    if not c['value']:
                        c['value'] = ss[k + 1]
                    break
                if ss[k] == 'RefDes':
                    break
            if not is_sch:
                c['value'] = ''      # PCB binary: attribute order is not reliable per component
    for c in comps.values():
        for k in ('value', 'type', 'pattern'):
            v = c[k]
            if v in ('{Value}', 'Value', '{Type}') or not re.match(r'^[\w.+\-/\\%#() ,~&]+$', v) \
                    or (len(v) <= 3 and not re.search(r'\d|^[A-Z]+$', v)):
                c[k] = ''
    # title block
    tb = {}
    for i, s in enumerate(ss):
        if s in PCAD_FIELDSET and s not in tb and i + 1 < len(ss):
            v = ss[i + 1].strip()
            if v and v not in PCAD_FIELDSET and len(v) > 1 and _wordy(v, 2) and v not in PCAD_JUNK \
                    and v not in ('Rev', 'Note', 'Notes', 'Size', 'Sheet', 'Name', 'of', 'Of', 'Drawn by', 'Date'):
                tb[s] = v
            elif s in PCAD_FIELDS:
                tb.setdefault(s, '')
    tb = {k: v for k, v in tb.items() if v and k in PCAD_FIELDS}
    # layers (pcb)
    layer_names = []
    for s in ('Top', 'Bottom', 'Board', 'Top Mask', 'Bot Mask', 'Top Silk', 'Bot Silk', 'Top Paste',
              'Bot Paste', 'Top Assy', 'Bot Assy'):
        if s in ss:
            layer_names.append(s)
    extra_layers = []
    if not is_sch:
        try:
            k = ss.index('Bot Assy')
            for s in ss[k + 1:k + 120]:
                if s in ('Default pad style', '(Default)'):
                    break
                if s not in PCAD_JUNK and re.match(r'^[A-Za-z][\w \-]{1,20}$', s) and not s.endswith('mil'):
                    extra_layers.append(s)
        except ValueError:
            pass
    extra_layers = _uniq(extra_layers)
    # other readable text
    used = set(comps) | {c['type'] for c in comps.values()} | {c['value'] for c in comps.values()} | set(libs)
    other = []
    for s in ss:
        s2 = s.strip()
        if s2 in used or s2 in PCAD_JUNK or s2 in PCAD_FIELDSET:
            continue
        if re.match(r'^(P:|T:H|\(|PS$|.*\[\d+\]$|.*mil$|\d+(\.\d+)?$)', s2):
            continue
        if _wordy(s2, 4) or (' ' in s2 and _wordy(s2, 3)):
            other.append(s2)
    other = _uniq(other)
    rows = sorted(comps.items(), key=lambda kv: _natkey(kv[0]))
    pcb_pats, pcb_vals = [], []
    if not is_sch:
        for i, s_ in enumerate(ss[:-1]):
            if ss[i + 1] == 'Primary' and len(s_) >= 3 and s_ != 'Primary' and _wordy(s_, 2) is not None \
                    and re.match(r'^[\w.+\-/() ]+$', s_):
                pcb_pats.append(s_)
            if s_ == 'Value' and re.match(r'^[\w.+\-/\\%]+$', ss[i + 1]) and ss[i + 1] not in ('{Value}', 'Value') \
                    and (re.match(r'^\.?\d[\d.]*(?:[pnumkfhvrKMRFHVWG%]{1,3}\d*)?(?:[/\\][\d.]+[a-zA-Z]{0,2})?$', ss[i + 1])
                         or re.match(r'^[A-Z][A-Z0-9_\-/.]{2,}$', ss[i + 1])):
                pcb_vals.append(ss[i + 1])
        pcb_pats = sorted(set(pcb_pats), key=_natkey)
        pcb_vals = sorted(set(pcb_vals), key=_natkey)
    pars = []
    if tb:
        pars.append({'heading': 'Title block'})
        pars.extend(f'{k}: {v}' for k, v in tb.items())
    if rows and not is_sch:
        pars.append({'heading': f'Component designators ({len(rows)})'})
        pars.append(', '.join(r for r, _ in rows))
        if pcb_pats:
            pars.append({'heading': f'Footprint patterns placed ({len(pcb_pats)})'}); pars.append(', '.join(pcb_pats))
        if pcb_vals:
            pars.append({'heading': f'Component values ({len(pcb_vals)})'}); pars.append(', '.join(pcb_vals))
        rows_out = []
    elif rows:
        pars.append({'heading': f'Components ({len(rows)})'})
        for ref, c in rows:
            pars.append(' — '.join(x for x in (ref, c['type'], c['value'] and 'value ' + c['value'],
                                               c['pattern'] and 'pattern ' + c['pattern']) if x))
    if libs:
        pars.append({'heading': 'Libraries'}); pars.append(', '.join(libs))
    if extra_layers and not is_sch:
        pars.append({'heading': 'Layers'}); pars.append(', '.join(layer_names + extra_layers))
    if other:
        pars.append({'heading': 'Other readable text (best effort)'})
        pars.append('\n'.join(other[:800]))
    kind = 'schematic' if is_sch else 'PCB layout'
    title = tb.get('Title', '')
    s = (f'{ver or "P-CAD"} binary {kind}' + (f' "{title}"' if title else '')
         + (f', drawing {tb["Drawing Number"]}' if tb.get('Drawing Number') else '')
         + f': {len(rows)} components recovered')
    vals = [c['value'] or c['type'] for _, c in rows if c['value'] or c['type']] if is_sch else pcb_vals
    if vals:
        s += ' (' + _join(_uniq(vals), 12) + ')'
    s += '.'
    if not is_sch and pcb_pats:
        s += ' Footprints: ' + _join(pcb_pats, 12) + '.'
    meta = [('Format', ver or 'P-CAD binary'), ('Components (recovered)', len(rows))]
    meta += [(k, v) for k, v in tb.items()][:6]
    if libs:
        meta.append(('Libraries', ', '.join(libs[:10])))
    return _result(type=f'P-CAD binary {kind}', title=title, summary=s, paragraphs=pars, meta=meta,
                   keywords=[title] + [k for k in tb.get('Drawing Number', '').split()] + _uniq(vals)[:10]
                   + _uniq(c['type'] for _, c in rows if c['type'])[:6] + pcb_pats[:6] + libs[:2],
                   notes=['P-CAD binary format: content recovered heuristically from embedded strings.'])


def _sexp_blocks(text, tag):
    """Yield (name, body) for '(tag "name" ...)' top-level-ish blocks using paren matching."""
    for m in re.finditer(r'\(' + tag + r' "((?:[^"\\]|\\.)*)"', text):
        start = m.start()
        depth, i, n = 0, start, len(text)
        inq = False
        while i < n:
            ch = text[i]
            if inq:
                if ch == '\\':
                    i += 1
                elif ch == '"':
                    inq = False
            elif ch == '"':
                inq = True
            elif ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        yield m.group(1), text[start:i + 1]


def _unesc(v):
    return re.sub(r'\\(.)', r'\1', v or '')


def accel_ascii(path, data):
    text = _dec(data)
    head = text[:2000]
    prog = re.search(r'\(program "([^"]*)" "([^"]*)"\)', head)
    prog = f'{prog.group(1)} {prog.group(2)}' if prog else 'ACCEL/P-CAD'
    units = re.search(r'\(fileUnits (\w+)\)', head)
    is_net = '(netlist' in text[:5000] and '(pcbDesign' not in text and '(schematicDesign' not in text
    is_sch = '(schematicDesign' in text or 'Schematic' in prog
    comps = []
    for name, body in _sexp_blocks(text, 'compInst'):
        g = lambda t: _unesc((re.search(r'\(' + t + r' "((?:[^"\\]|\\.)*)"', body) or [None, ''])[1])
        comps.append({'ref': name, 'type': g('originalName') or g('compRef'), 'value': g('compValue'),
                      'pattern': g('patternName')})
    nets = []
    for name, body in _sexp_blocks(text, 'net'):
        nodes = re.findall(r'\(node "([^"]*)" "([^"]*)"\)', body)
        nets.append((name, [f'{a}-{b}' for a, b in nodes]))
    # pcb pattern placement gives patterns for refs
    pats = dict((b, a) for a, b in re.findall(r'\(patternRef "([^"]*)"\) \(refDesRef "([^"]*)"\)', text))
    for c in comps:
        if not c['pattern'] and c['ref'] in pats:
            c['pattern'] = re.sub(r'_\d+$', '', pats[c['ref']])
        if c['value'] in ('{Value}',):
            c['value'] = ''
    fields = re.findall(r'\(fieldDef "((?:[^"\\]|\\.)*)" "((?:[^"\\]|\\.)*)"\)', text)
    tb = [(_unesc(k), _unesc(v)) for k, v in _uniq(fields) if v]
    layers = _uniq(re.findall(r'\(layerDef "([^"]*)"', text))
    libs = _uniq(re.findall(r'\(sourceLibrary "([^"]*)"\)', text))
    sheets = _uniq(re.findall(r'\(sheet "([^"]*)" \(sheetNum', text))
    texts = []
    for t in re.findall(r'\(text \(pt [^)]*\) "((?:[^"\\]|\\.)*)"', text):
        if t and not re.match(r'^\d{1,3}$', t):
            texts.append(_unesc(t))
    pinish = set(re.findall(r'\(pin(?:Des|Name) \(text \(pt [^)]*\) "((?:[^"\\]|\\.)*)"', text))
    texts = [t for t in _uniq(texts) if t not in pinish]
    ports = _uniq(re.findall(r'\(port \(pt [^)]*\) \(portType \w+\) \(portPinLength \w+\) \(netNameRef "([^"]*)"', text))
    # board extents from boardOutline/ board layer lines is hard; use all pt values on 'Board' layer contents
    size = None
    m = re.search(r'\(layerContents \(layerNumRef 3\)(.*?)\n  \)', text, re.S)
    pars = []
    if tb:
        pars.append({'heading': 'Title block'}); pars.extend(f'{k}: {v}' for k, v in tb)
    comps.sort(key=lambda c: _natkey(c['ref']))
    if comps:
        pars.append({'heading': f'Components ({len(comps)})'})
        for c in comps:
            pars.append(' — '.join(x for x in (c['ref'], c['type'], c['value'] and 'value ' + c['value'],
                                               c['pattern'] and 'pattern ' + c['pattern']) if x))
    if nets:
        pars.append({'heading': f'Nets ({len(nets)})'})
        for n, nodes in sorted(nets, key=lambda x: _natkey(x[0])):
            pars.append(f'{n}: ' + ' '.join(nodes))
    if sheets:
        pars.append({'heading': 'Sheets'}); pars.append(', '.join(sheets))
    if layers:
        pars.append({'heading': 'Layers'}); pars.append(', '.join(layers))
    if libs:
        pars.append({'heading': 'Source libraries'}); pars.append(', '.join(libs))
    if texts:
        pars.append({'heading': 'Drawing text'}); pars.extend(texts[:1000])
    kind = 'netlist' if is_net else 'schematic' if is_sch else 'PCB layout'
    title = dict(tb).get('Title', '')
    dn = dict(tb).get('Drawing Number', '')
    named = [n for n, _ in nets if not re.match(r'^NET\d+$', n)]
    s = (f'{prog} ACCEL ASCII {kind}' + (f' "{title}"' if title else '') + (f', drawing {dn}' if dn else '')
         + f': {len(comps)} components, {len(nets)} nets')
    if layers and not is_sch:
        s += f', {len(layers)} layers'
    s += '.'
    vals = [c['value'] or c['type'] for c in comps if c['value'] or c['type']]
    if vals:
        s += ' Parts include ' + _join(_uniq(vals), 12) + '.'
    if named:
        s += ' Named nets: ' + _join(named, 15) + '.'
    meta = [('Program', prog), ('Units', units.group(1) if units else ''), ('Components', len(comps)),
            ('Nets', len(nets))] + tb[:6]
    meta = [(k, v) for k, v in meta if v != '']
    return _result(type=f'ACCEL/P-CAD ASCII {kind}', title=title, summary=s, paragraphs=pars, meta=meta,
                   keywords=[x for x in (title, dn) if x] + _uniq(vals)[:8] + named[:4]
                   + _uniq(c['pattern'] for c in comps if c['pattern'])[:6] + _uniq(c['type'] for c in comps if c['type'])[:6])


def tango_pcb(path, data):
    text = _dec(data)
    lines = text.splitlines()
    ver = lines[0].lstrip(';').strip() if lines else 'Tango-PCB'
    comps, texts, cnt = [], [], collections.Counter()
    board = None
    for l in lines:
        t = l.split(' ', 1)[0]
        cnt[t] += 1
        if t == 'COMP':
            q = re.findall(r'"([^"]*)"', l)
            if q:
                comps.append((q[0], q[1] if len(q) > 1 else '', q[3] if len(q) > 3 else ''))
        elif t == 'TEXT':
            q = re.findall(r'"([^"]*)"', l)
            if q and q[0].strip():
                texts.append(q[0])
        elif t == 'BOARD':
            nums = [int(x) for x in re.findall(r'-?\d+', l)[:4]]
            if len(nums) == 4:
                board = (abs(nums[2] - nums[0]), abs(nums[3] - nums[1]))
    comps.sort(key=lambda c: _natkey(c[0]))
    pars = [{'heading': f'Components ({len(comps)})'}]
    pars += [' — '.join(x for x in (r, v and 'value ' + v, p and 'pattern ' + p) if x) for r, v, p in comps]
    tx = _uniq(texts)
    if tx:
        pars.append({'heading': 'Board text'}); pars.extend(tx)
    pats = _uniq(p for _, _, p in comps if p)
    s = f'{ver} ASCII PCB layout: {len(comps)} components' + (f', board {_size_str(*board)}' if board else '') + '.'
    if pats:
        s += ' Patterns: ' + _join(pats, 15) + '.'
    meta = [('Format', ver), ('Components', len(comps)), ('Pads', cnt['PAD']), ('Tracks/lines', cnt['LINE'])]
    if board:
        meta.append(('Board extent', _size_str(*board)))
    return _result(type='Tango-PCB ASCII layout', summary=s, paragraphs=pars, meta=meta, keywords=pats[:15])


def tango_netlist(path, data):
    text = _dec(data)
    comps, nets = [], []
    for m in re.finditer(r'\[(.*?)\]', text, re.S):
        f = [x.strip() for x in m.group(1).splitlines()]
        f = [x for x in f]
        while f and not f[0]:
            f.pop(0)
        if f:
            comps.append((f[0], f[1] if len(f) > 1 else '', f[2] if len(f) > 2 else '', f[3] if len(f) > 3 else ''))
    for m in re.finditer(r'\((.*?)\)', text, re.S):
        f = [x.strip() for x in m.group(1).splitlines() if x.strip()]
        if f:
            nets.append((f[0], f[1:]))
    if not comps and not nets:
        return _generic_text(path, 'Netlist', data)
    comps.sort(key=lambda c: _natkey(c[0]))
    pars = [{'heading': f'Components ({len(comps)})'}]
    for r, p, t, v in comps:
        pars.append(' — '.join(x for x in (r, t, v and 'value ' + v, p and 'pattern ' + p) if x))
    pars.append({'heading': f'Nets ({len(nets)})'})
    for n, nodes in sorted(nets, key=lambda x: _natkey(x[0])):
        pars.append(f'{n}: ' + ' '.join(nodes))
    named = [n for n, _ in nets if not re.match(r'^(NET|N)\d+$|^Net\w+_\d+$', n)]
    vals = [v or t for _, _, t, v in comps if v or t]
    s = f'Tango/Protel-format netlist: {len(comps)} components, {len(nets)} nets.'
    if vals:
        s += ' Parts include ' + _join(_uniq(vals), 12) + '.'
    if named:
        s += ' Named nets: ' + _join(named, 15) + '.'
    return _result(type='PCB netlist (Tango/Protel format)', summary=s, paragraphs=pars,
                   meta=[('Components', len(comps)), ('Nets', len(nets))],
                   keywords=_uniq(vals)[:8] + named[:5] + _uniq(p for _, p, _, _ in comps if p)[:5])


def ipc356(path, data):
    text = _dec(data)
    hdr, comments, nets, refs = [], [], collections.OrderedDict(), set()
    aliases = {}
    tests = 0
    for l in text.splitlines():
        if l.startswith('P '):
            hdr.append(l[2:].strip())
            m = re.match(r'P\s+(NNAME\d+)\s+(\S+)', l)
            if m:
                aliases[m.group(1)] = m.group(2)
        elif l.startswith('C '):
            if l[2:].strip():
                comments.append(l[2:].rstrip())
        elif l[:3] in ('317', '327', '017', '027'):
            tests += 1
            net = l[3:17].strip()
            net = aliases.get(net, net)
            ref = l[20:26].strip()
            pin = l[27:31].strip()
            if ref and ref != 'VIA':
                refs.add(ref)
            nets.setdefault(net, []).append(f'{ref}-{pin}' if pin else ref)
    pars = []
    if hdr:
        pars.append({'heading': 'Header'}); pars.extend(hdr)
    if comments:
        pars.append({'heading': 'Comments'}); pars.append('\n'.join(comments[:200]))
    pars.append({'heading': f'Nets ({len(nets)})'})
    for n, nodes in nets.items():
        pars.append(f'{n}: ' + ' '.join(_uniq(nodes)))
    named = [n for n in nets if not re.match(r'^N\d+$|^NET\d+$|^Net\w+_\d+$', n)]
    s = f'IPC-D-356 bare-board test netlist: {len(nets)} nets, {len(refs)} components, {tests} test points.'
    if named:
        s += ' Nets include ' + _join(named, 15) + '.'
    return _result(type='IPC-D-356 netlist', summary=s, paragraphs=pars,
                   meta=[('Nets', len(nets)), ('Components', len(refs)), ('Test points', tests)],
                   keywords=named[:10])

# ---------------------------------------------------------------- reports (BOM / PnP)

def _fixed_table(lines):
    """Find 'header' + '----' lines and split rows by the dash column spans."""
    for i in range(1, len(lines)):
        if re.match(r'^\s*-{3,}[\s-]*$', lines[i]) and lines[i - 1].strip():
            dash = lines[i]
            spans = [(m.start(), m.end()) for m in re.finditer(r'-+', dash)]
            hdrline = lines[i - 1]
            if len(spans) == 1:
                # single long dash line: derive spans from header word starts
                starts = [m.start() for m in re.finditer(r'\S+', hdrline)]
                spans = [(s, (starts[k + 1] if k + 1 < len(starts) else 10000)) for k, s in enumerate(starts)]
            else:
                spans = [(s, (spans[k + 1][0] if k + 1 < len(spans) else 10000)) for k, (s, e) in enumerate(spans)]
            heads = [hdrline[a:b].strip() or f'col{k}' for k, (a, b) in enumerate(spans)]
            rows = []
            for l in lines[i + 1:]:
                if not l.strip():
                    continue
                if re.match(r'^\s*[-=]{5,}', l):
                    break
                cells = [l[a:b].strip() for a, b in spans]
                # tolerate right-aligned numbers spilling left: fallback split
                rows.append(cells)
            return heads, rows, lines[:i - 1]
    return None, [], lines


def report_table(path, data):
    text = _dec(data)
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    first = next((l.strip() for l in lines if l.strip()), '')
    if first.startswith('"') or (first.count(',') >= 2 and not re.search(r'\s{3,}', first)):
        return csv_table(path, text, first)
    heads, rows, pre = _fixed_table(lines)
    if not heads:
        return _generic_text(path, 'EDA report', data)
    pnp = 'pick' in first.lower() or any(h.lower() in ('locationx', 'x', 'center-x(mil)', 'mid x') for h in heads)
    hl = [h.lower() for h in heads]

    def col(*names):
        for n in names:
            for k, h in enumerate(hl):
                if h == n or h.startswith(n):
                    return k
        return None
    ci_ref = col('refdes', 'designator', 'components', 'reference')
    ci_val = col('value', 'comment')
    ci_part = col('componentname', 'type', 'part', 'description')
    ci_pat = col('patternname', 'pattern', 'footprint')
    ci_cnt = col('count', 'quantity', 'qty')
    # merge BOM continuation lines (only refdes column filled)
    merged = []
    for r in rows:
        nonempty = [k for k, c in enumerate(r) if c]
        if merged and ci_ref is not None and nonempty and all(k in (ci_ref, len(r) - 1) or not r[k] for k in nonempty) \
                and (ci_cnt is None or not r[ci_cnt]) and (ci_val is None or not r[ci_val]):
            merged[-1][ci_ref] = (merged[-1][ci_ref] + ', ' + r[ci_ref]).strip(', ')
            continue
        merged.append(list(r))
    refs, parts = [], []
    pars = []
    meta_pre = [l.strip() for l in pre if l.strip() and not set(l.strip()) <= set('=-')]
    if meta_pre:
        pars.append({'heading': 'Header'}); pars.extend(meta_pre)
    pars.append({'heading': f'{"Placements" if pnp else "Lines"} ({len(merged)})'})
    for r in merged:
        pars.append(' · '.join(f'{h}: {c}' for h, c in zip(heads, r) if c))
        if ci_ref is not None and r[ci_ref]:
            refs += [x for x in re.split(r'[,\s]+', r[ci_ref]) if x]
        for ci in (ci_val, ci_part):
            if ci is not None and ci < len(r) and r[ci]:
                parts.append(r[ci])
    parts = [p for p in parts if p not in ('Value', '{Value}', '*')]
    up = _uniq(parts)
    qty = 0
    if ci_cnt is not None:
        for r in merged:
            try:
                qty += int(float(r[ci_cnt]))
            except Exception:
                pass
    first = re.sub(r'\s{2,}', ' — ', first)
    title = ' '.join(meta_pre[1:2]) if len(meta_pre) > 1 else ''
    if pnp:
        sides = collections.Counter(r[col('layer', 'side') or 0] for r in merged) if col('layer', 'side') is not None else {}
        s = (f'{first}: {len(merged)} component placements'
             + (' (' + ', '.join(f'{v} {k.lower()}' for k, v in sides.items() if k) + ')' if sides else '') + '.')
        typ = 'Pick-and-place / centroid file'
    else:
        s = f'{first}: {len(merged)} BOM lines covering {len(refs) or qty} components.'
        typ = 'Bill of materials'
    if up:
        s += ' Parts: ' + _join(up, 15) + '.'
    pn = [p for p in up if core.PARTNO.match(p)]
    return _result(type=typ, title=title, summary=s, paragraphs=pars, keywords=pn[:10] + up[:5],
                   meta=[('Columns', ', '.join(heads)), ('Rows', len(merged)), ('Component references', len(refs)),
                         ('Unique values/parts', len(up))])


def csv_table(path, text, first):
    rows = list(csv.reader(io.StringIO(text)))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return _generic_text(path, 'CSV report', text.encode())
    heads = [h.strip() for h in rows[0]]
    body = rows[1:]
    pars = [{'heading': f'Rows ({len(body)})'}]
    for r in body:
        pars.append(' · '.join(f'{h}: {c}' for h, c in zip(heads, r) if c.strip()))
    hl = [h.lower() for h in heads]
    vals = []
    for name in ('value', 'componentname', 'part', 'comment', 'description'):
        if name in hl:
            vals += [r[hl.index(name)] for r in body if len(r) > hl.index(name) and r[hl.index(name)]]
    up = _uniq(vals)
    s = f'Bill of materials / report (CSV) with {len(body)} rows; columns {", ".join(heads)}.'
    if up:
        s += ' Parts: ' + _join(up, 15) + '.'
    more = []
    for name in ('componentname', 'patternname', 'footprint', 'description'):
        if name in hl:
            more += [r[hl.index(name)] for r in body if len(r) > hl.index(name) and r[hl.index(name)]]
    return _result(type='Bill of materials (CSV)', summary=s, paragraphs=pars, keywords=up[:10] + _uniq(more)[:10],
                   meta=[('Rows', len(body)), ('Columns', ', '.join(heads))])

# ---------------------------------------------------------------- Gerber / drill

LAYER_FN = {
    'gtl': 'top copper', 'gbl': 'bottom copper', 'gto': 'top silkscreen', 'gbo': 'bottom silkscreen',
    'gts': 'top solder mask', 'gbs': 'bottom solder mask', 'gtp': 'top paste', 'gbp': 'bottom paste',
    'gko': 'keep-out', 'gpt': 'top pad master', 'gpb': 'bottom pad master', 'gd1': 'drill drawing',
    'gg1': 'drill guide', 'top': 'top copper', 'bot': 'bottom copper', 'gnd': 'ground plane',
    'gnd1': 'ground plane 1', 'gnd2': 'ground plane 2', 'pwr': 'power plane', 'in1': 'inner layer 1',
    'in2': 'inner layer 2', 'drl': 'drill drawing', 'brd': 'board outline', 'sst': 'top silkscreen',
    'ssb': 'bottom silkscreen', 'smt': 'top solder mask', 'smb': 'bottom solder mask', 'stn': 'paste stencil',
}


def _layer_from_name(name, ext):
    e = ext.lower()
    if e in LAYER_FN:
        return LAYER_FN[e]
    m = re.match(r'gm(\d+)$', e)
    if m:
        return f'mechanical layer {m.group(1)}'
    m = re.match(r'g(\d+)$', e)
    if m:
        return f'mid signal layer {m.group(1)}'
    m = re.match(r'gp(\d+)$', e)
    if m:
        return f'internal plane {m.group(1)}'
    n = name.lower()
    for k, v in (('paste_top', 'top paste'), ('paste_bot', 'bottom paste'), ('mask_top', 'top solder mask'),
                 ('mask_bot', 'bottom solder mask'), ('silk_top', 'top silkscreen'), ('silk_bot', 'bottom silkscreen'),
                 ('top', 'top copper/side'), ('bot', 'bottom copper/side'), ('drill', 'drill'), ('outline', 'board outline'),
                 ('silk', 'silkscreen'), ('mask', 'solder mask'), ('paste', 'paste'), ('gnd', 'ground plane'),
                 ('pwr', 'power plane')):
        if k in n:
            return v
    m = re.match(r'l(\d+)', n)
    if m:
        return f'layer {m.group(1)}'
    return ''


def gerber(path, data):
    text = _dec(data)
    name = os.path.basename(path)
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if ext == 'gbr' and '.' in name[:-4]:
        ext2 = name[:-4].rsplit('.', 1)[-1].lower()
    comments = []
    for m in re.finditer(r'G0?4\s?([^*]*)\*', text[:400000]):
        c = m.group(1).strip()
        if c:
            comments.append(c)
    fs = re.search(r'%FS([LTD]?)([AI]?)N?\d*G?\d*D?\d*X(\d)(\d)Y(\d)(\d)', text)
    mo = re.search(r'%MO(IN|MM)', text)
    unit = mo.group(1) if mo else None
    if not unit:
        if re.search(r'G71\*', text[:20000]) or re.search(r'(?i)metric|millimet', ' '.join(comments[:40])):
            unit = 'MM'
        else:
            unit = 'IN'
    if fs:
        zero, ip, xd = fs.group(1) or 'L', fs.group(2), int(fs.group(4))
        ints = int(fs.group(3))
        yd = int(fs.group(6))
    else:
        cm = re.search(r'Numeric Format:\s*(\d)\.(\d)', ' '.join(comments))
        ints, xd = (int(cm.group(1)), int(cm.group(2))) if cm else (2, 4)
        yd = xd
        zero = 'T' if re.search(r'Trailing-Zero', ' '.join(comments)) else 'L'
    lnames = re.findall(r'%LN([^*%]*)\*', text)
    inname = re.findall(r'%IN([^*%]*)\*', text)
    attrs = re.findall(r'%TF\.?([^,*]+),?([^*]*)\*%', text)
    func = ''
    for k, v in attrs:
        if k.lower().endswith('filefunction'):
            func = v.replace(',', ' ')
    aps = re.findall(r'%ADD(\d+)([A-Za-z_][\w.]*)', text)
    apshapes = collections.Counter(s.upper()[0] if s[:2].upper() not in ('OC',) else 'OC' for _, s in aps)
    macros = re.findall(r'%AM([^*]+)\*', text)
    xs, ys = [], []

    def conv(s, d):
        neg = s.startswith('-'); s = s.lstrip('+-')
        if '.' in s:
            v = float(s)
        elif zero == 'T':
            s = s.ljust(ints + d, '0'); v = int(s) / 10 ** d
        else:
            v = int(s) / 10 ** d
        return -v if neg else v
    flashes = draws = 0
    body = re.sub(r'%[^%]*%', '', text)
    body = re.sub(r'G0?4[^*]*\*', '', body)
    for m in re.finditer(r'(?:X([+-]?[\d.]+))?(?:Y([+-]?[\d.]+))?(?:I[+-]?[\d.]+)?(?:J[+-]?[\d.]+)?(D0?[123])?\*', body):
        if m.group(1):
            xs.append(conv(m.group(1), xd))
        if m.group(2):
            ys.append(conv(m.group(2), yd))
        d = m.group(3)
        if d and d.endswith('3'):
            flashes += 1
        elif d and d.endswith('1'):
            draws += 1
    layer = func or _layer_from_name(name, ext)
    src = ''
    for c in comments:
        m = re.match(r'Source:\s*(.*)', c)
        if m:
            src = m.group(1); break
    if not src:
        for c in comments[:5]:
            if re.search(r'(?i)altium|p-cad|pads|cam350|allegro|eagle|protel|orcad|kicad|gerber', c):
                src = c; break
    u = 'in' if unit == 'IN' else 'mm'
    size = ''
    if len(xs) > 1 and len(ys) > 1:
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if 0 < w < (100 if u == 'in' else 2540):
            size = f'{_fmt(w)} x {_fmt(h)} {u}'
    fmt_s = ('RS-274X' if (aps or fs or mo) and '%' in text[:20000] else 'RS-274-D')
    s = f'Gerber {fmt_s} photoplot' + (f' — {layer}' if layer else '')
    if size:
        s += f', image extent {size}' + ('' if fs or re.search(r'Numeric Format', ' '.join(comments)) else ' (coordinate format assumed)')
    s += f', {len(aps)} apertures'
    if flashes or draws:
        s += f', {flashes:,} flashes and {draws:,} draws'
    s += '.'
    if src:
        s += f' Generated by {src}.'
    if lnames:
        s += ' Layer name: ' + ', '.join(_uniq(lnames)) + '.'
    pars = []
    if comments:
        pars.append({'heading': 'Header comments'})
        pars.append('\n'.join(_uniq(comments)[:300]))
    if aps:
        pars.append({'heading': f'Apertures ({len(aps)})'})
        apdefs = re.findall(r'%ADD(\d+)([^*]*)\*%', text)
        shp = {'C': 'circle', 'R': 'rectangle', 'O': 'obround', 'P': 'polygon'}

        def apdesc(b):
            m = re.match(r'([CROP]),([\d.]+)(?:X([\d.]+))?', b.strip())
            if m:
                return f"{shp[m.group(1)]} {m.group(2)}" + (f" × {m.group(3)}" if m.group(3) else '')
            return 'macro ' + b.strip()
        pars.append('; '.join(f'D{a} {apdesc(b)}' for a, b in apdefs[:600]))
    meta = [('Layer function', layer or 'unknown'), ('Format', fmt_s), ('Units', 'inch' if u == 'in' else 'mm'),
            ('Coordinate format', f'{ints}.{xd}, {"trailing" if zero == "T" else "leading"}-zero suppression'),
            ('Apertures', len(aps)), ('Aperture macros', len(macros)), ('Flashes', flashes), ('Draws', draws)]
    if size:
        meta.append(('Image extent', size))
    if inname:
        meta.append(('Image name', ', '.join(_uniq(inname))))
    if src:
        meta.append(('Source', src))
    stem = os.path.splitext(name)[0]
    prog = re.match(r'([A-Za-z][\w\- ]*?)(?:,| V\d| Version| \(|$)', src or '')
    kws = [x for x in (layer, stem, 'Gerber', fmt_s, prog.group(1).strip() if prog else '',
                       *(_uniq(lnames)[:2]), *(_uniq(inname)[:1])) if x]
    kws += ['photoplot', 'apertures', 'circle', 'rectangle', 'flashes', 'draws', 'inch' if u == 'in' else 'mm']
    return _result(type='Gerber photoplot' + (f' ({layer})' if layer else ''), summary=s, meta=meta,
                   paragraphs=pars, keywords=kws)


def excellon(path, data):
    text = _dec(data)
    unit = 'inch'
    if re.search(r'METRIC|M71', text[:5000]):
        unit = 'mm'
    tools = collections.OrderedDict()
    for m in re.finditer(r'^T(\d+)(?:[FS]\d+)*C([\d.]+)', text, re.M):
        tools[int(m.group(1))] = float(m.group(2))
    hits = collections.Counter()
    cur = None
    body_start = text.find('%', text.find('M48')) if 'M48' in text else 0
    for l in text[max(0, body_start):].splitlines():
        l = l.strip()
        m = re.match(r'^T(\d+)(?:C[\d.]+)?$', l)
        if m:
            cur = int(m.group(1)); continue
        if (l.startswith('X') or l.startswith('Y')) and cur is not None:
            hits[cur] += 1
    comments = [l[1:].strip() for l in text.splitlines()[:200] if l.startswith(';') and l[1:].strip()]
    pars = []
    if comments:
        pars.append({'heading': 'Header comments'}); pars.append('\n'.join(comments))
    pars.append({'heading': 'Tool table'})
    for t in sorted(set(tools) | set(hits)):
        d = tools.get(t)
        ds = f'{_fmt(d, 4)} {unit}' + (f' ({_fmt(d * 25.4, 3)} mm)' if d and unit == 'inch' else '') if d else '?'
        pars.append(f'T{t}: {ds}, {hits.get(t, 0)} holes')
    total = sum(hits.values())
    s = f'Excellon NC drill file: {len(set(tools) | set(hits))} tools, {total:,} holes'
    if tools:
        s += f', sizes {_fmt(min(tools.values()), 4)}–{_fmt(max(tools.values()), 4)} {unit}'
    s += '.'
    if comments:
        s += ' ' + comments[0][:150]
    return _result(type='Excellon NC drill', summary=s, paragraphs=pars,
                   meta=[('Units', unit), ('Tools', len(set(tools) | set(hits))), ('Holes', total)])

# ---------------------------------------------------------------- mechanical CAD

def dxf(path, data):
    cpm = re.search(rb'\$DWGCODEPAGE\s*\r?\n\s*3\s*\r?\n\s*(\S+)', data[:200000])
    cp = {b'ANSI_936': 'gbk', b'ANSI_932': 'cp932', b'ANSI_949': 'cp949', b'ANSI_950': 'big5',
          b'ANSI_1251': 'cp1251', b'ANSI_1250': 'cp1250'}.get(cpm.group(1).upper() if cpm else b'')
    text = None
    if cp:
        try:
            text = data.decode(cp)
        except Exception:
            text = data.decode(cp, 'replace')
    if text is None:
        text = _dec(data)
    L = text.splitlines()
    n = len(L) - (len(L) % 2)
    pairs = [(L[i].strip(), L[i + 1].rstrip('\r')) for i in range(0, n, 2)]
    hdr = {}
    layers, ents, texts, blocks = [], collections.Counter(), [], []
    section = None
    i, N = 0, len(pairs)
    cur = None
    in_tables = False
    while i < N:
        c, v = pairs[i]
        if c == '0':
            if cur is not None:
                _dxf_flush(cur, texts)
            cur = None
            if v == 'SECTION' and i + 1 < N and pairs[i + 1][0] == '2':
                section = pairs[i + 1][1].strip(); i += 2; continue
            if v == 'ENDSEC':
                section = None
            elif section == 'TABLES' and v == 'LAYER':
                for j in range(i + 1, min(i + 40, N)):
                    if pairs[j][0] == '2':
                        layers.append(pairs[j][1].strip()); break
                    if pairs[j][0] == '0':
                        break
            elif section in ('ENTITIES', 'BLOCKS'):
                ents[v] += 1 if section == 'ENTITIES' else 0
                if v == 'BLOCK':
                    for j in range(i + 1, min(i + 30, N)):
                        if pairs[j][0] == '2':
                            blocks.append(pairs[j][1].strip()); break
                if v in ('TEXT', 'MTEXT', 'ATTRIB', 'ATTDEF', 'DIMENSION'):
                    cur = {'t': v, '1': '', '3': [], 'layer': ''}
        elif section == 'HEADER' and c == '9':
            var = v.strip(); vals = {}
            j = i + 1
            while j < N and pairs[j][0] not in ('9', '0'):
                vals[pairs[j][0]] = pairs[j][1].strip(); j += 1
            hdr[var] = vals
            i = j; continue
        elif cur is not None:
            if c == '1':
                cur['1'] = v
            elif c == '3':
                cur['3'].append(v)
            elif c == '8':
                cur['layer'] = v.strip()
        i += 1
    if cur is not None:
        _dxf_flush(cur, texts)
    ver = hdr.get('$ACADVER', {}).get('1', '')
    ext = None
    try:
        mn, mx = hdr['$EXTMIN'], hdr['$EXTMAX']
        ext = (float(mn['10']), float(mn['20']), float(mx['10']), float(mx['20']))
        if abs(ext[0]) > 1e19 or ext[2] < ext[0]:
            ext = None
    except Exception:
        ext = None
    units = {'1': 'in', '2': 'ft', '4': 'mm', '5': 'cm', '6': 'm'}.get(hdr.get('$INSUNITS', {}).get('70', ''), '')
    pars = []
    tx = [t for t in texts if t.strip()]
    if tx:
        pars.append({'heading': f'Text entities ({len(tx)})'})
        pars.extend(tx)
    if layers:
        pars.append({'heading': f'Layers ({len(layers)})'}); pars.append(', '.join(layers))
    ub = [b for b in _uniq(blocks) if not b.startswith('*')]
    if ub:
        pars.append({'heading': 'Blocks'}); pars.append(', '.join(ub[:500]))
    total = sum(ents.values())
    s = f'AutoCAD DXF drawing{" (" + ver + ")" if ver else ""}: {total:,} entities on {len(layers)} layers'
    if ext:
        s += f', extents {_fmt(ext[2] - ext[0])} x {_fmt(ext[3] - ext[1])}{(" " + units) if units else ""}'
    s += '.'
    ut = _uniq(t.replace('\n', ' ') for t in tx)
    ut = [t for t in ut if len(t) >= 3] + [t for t in ut if len(t) < 3]
    if ut:
        s += ' Text includes: ' + _join([t[:60] for t in ut], 12) + '.'
    meta = [('AutoCAD version', f'{ver} ({ACAD.get(ver, "?")})' if ver else 'unknown'),
            ('Entities', ', '.join(f'{k} {v}' for k, v in ents.most_common(12) if v)), ('Layers', len(layers))]
    if ext:
        meta.append(('Extents', f'({_fmt(ext[0])}, {_fmt(ext[1])}) – ({_fmt(ext[2])}, {_fmt(ext[3])}){(" " + units) if units else ""}'))
    return _result(type='AutoCAD DXF drawing', summary=s, paragraphs=pars, meta=meta,
                   keywords=[l for l in layers if l not in ('0', 'DEFPOINTS')][:6])


def _dxf_flush(cur, texts):
    t = ''.join(cur['3']) + cur['1']
    if cur['t'] == 'DIMENSION' and t in ('', '<>'):
        return
    if cur['t'] == 'MTEXT':
        t = re.sub(r'\\P', '\n', t)
        t = re.sub(r'\\[ACFHQTWfcp][^;\\{}]*;', '', t)
        t = re.sub(r'\\[LlOoKkNnS~]', '', t)
        t = t.replace('{', '').replace('}', '')
    t = re.sub(r'\\U\+([0-9A-Fa-f]{4})', lambda m: chr(int(m.group(1), 16)), t)
    t = t.replace('%%c', 'Ø').replace('%%d', '°').replace('%%p', '±').replace('%%C', 'Ø').replace('%%D', '°').replace('%%P', '±')
    t = re.sub(r'%%[uUoO]', '', t)
    texts.append(t.strip())


ACAD = {'AC1.50': 'R2.05', 'AC2.10': 'R2.10', 'AC1001': 'R2.2', 'AC1002': 'R2.5', 'AC1003': 'R2.6',
        'AC1004': 'R9', 'AC1006': 'R10', 'AC1009': 'R11/R12', 'AC1012': 'R13', 'AC1014': 'R14',
        'AC1015': 'AutoCAD 2000', 'AC1018': 'AutoCAD 2004', 'AC1021': 'AutoCAD 2007',
        'AC1024': 'AutoCAD 2010', 'AC1027': 'AutoCAD 2013', 'AC1032': 'AutoCAD 2018', 'AC0904': 'R9 (?)'}

DWG_SYS = re.compile(r'(AcDb|ACAD_|Acad|AcAd|ObjectDBX|Grid/|PageSettings|MultiPageSettings|UnitSettings|'
                     r'RTVS|AVE_|ASHADE|DIMASSOC|Shaded with|CONTINUOUS|Solid line|STANDARD|Standard|'
                     r'Model_Space|Paper_Space|DEFPOINTS|AutoCAD|\.shx|ByLayer|ByBlock|Visual|Conceptual|'
                     r'Realistic|Wireframe|Hidden|Normal|Annotative|Legacy|Plot|Layout|Dictionary|XRECORD|'
                     r'Material|Global|Flat|Gouraud|Brightness|Contrast|Shadow|Edge|Face|Basic|Section|'
                     r'Light|Render|Sky|Sun|Detail|Scale|Viewport|Gradient)', re.I)


DWG_DROP = {'RASTERVARIABLES', 'DSTYLE', 'DesignCenter Data', 'ACAD', 'ACDBDICTIONARYWDFLT', 'GROUP', 'DIMSTYLE',
            'MLINESTYLE', 'LTYPE', 'LAYER', 'STYLE', 'VPORT', 'APPID', 'UCS', 'BLOCK_RECORD', 'LAYOUT', 'PLOTSETTINGS',
            'DICTIONARY', 'DICTIONARYVAR', 'XRECORD', 'SCALE', 'SORTENTSTABLE', 'WIPEOUTVARIABLES', 'IDBUFFER',
            'SPATIAL_FILTER', 'SPATIAL_INDEX', 'LAYER_INDEX', 'PLACEHOLDER', 'VISUALSTYLE', 'MATERIAL', 'TABLESTYLE',
            'CELLSTYLEMAP', 'MLEADERSTYLE', 'DBCOLOR', 'ACDBPLACEHOLDER', 'ACDBDICTIONARYWDFLT', 'HATCH', 'MTEXT',
            'LWPOLYLINE', 'IMAGEDEF', 'IMAGEDEF_REACTOR', 'RASTERVARIABLES', 'OLE2FRAME', 'XREFPANEL', 'SECTIONVIEWSTYLE',
            'DETAILVIEWSTYLE', 'SUNSTUDY', 'ARCALIGNEDTEXT', 'RTEXT', 'WIPEOUT', 'ACDSRECORD', 'ACDSSCHEMA',
            'EXACXREFPANELOBJECT', 'NPOCOLLECTION', 'ACDBASSOCNETWORK', 'ACDBNAVISWORKSMODELDEF', 'ACDBSECTIONVIEWSTYLE'}


def dwg(path, data):
    ver = data[:6].decode('latin-1', 'replace')
    name = ACAD.get(ver, '')
    if data.startswith(b';Tango'):
        return tango_pcb(path, data)
    if not ver.startswith('AC') and not name:
        return _binary_note(path, 'DWG (unrecognised header)', data)
    notes = []
    found = collections.OrderedDict()
    if ver in ('AC1018', 'AC1021', 'AC1024', 'AC1027', 'AC1032'):
        notes.append(f'{name} DWG stores objects compressed; only uncompressed strings were scanned.')
    buf = data[:24_000_000]
    shifts = [0] if ver <= 'AC1009' else range(8)
    big = int.from_bytes(buf, 'big') if len(shifts) > 1 else None
    L = len(buf)
    for k in shifts:
        b = buf if k == 0 else ((big << k) & ((1 << (8 * L)) - 1)).to_bytes(L, 'big')
        for m in re.finditer(rb'[\x20-\x7e]{4,}', b):
            s = m.group().decode('latin-1').strip()
            s = re.sub(r'[^A-Za-z0-9).%"\]]+$', '', s)
            if len(s) < 4 or DWG_SYS.search(s):
                continue
            if not _wordy(s, 4):
                continue
            words = re.findall(r'[A-Za-z]{3,}', s)
            if not words:
                continue
            if ' ' not in s and len(s) < 6:
                continue
            m2 = re.match(r'^(.*[A-Z.:\'")])(?:[0@][A-Z]?|[0@]?[A-Z]?[a-z]{1,2}|[0@][A-Za-z][a-z]?)$', s)
            if m2 and len(m2.group(1)) >= 3 and m2.group(1).upper() == m2.group(1):
                s = m2.group(1)
            s = re.sub(r'%%[UuOo]', '', s.replace('\\P', ' ')).strip()
            s = re.split(r'["#@$]?0Q|\)Q#|"0Q|@P[A-Z]?$', s)[0].strip()
            if s in DWG_DROP or re.match(r'^(DAD|UDAD|0Q|0P|MTEXT|COLOR[A-Z]|SCENE)', s) or len(s) < 4 \
                    or re.match(r'^(BORDER|CENTER|DASHDOT|DASHED|DIVIDE|DOT|HIDDEN|PHANTOM)X?2?$', s):
                continue
            if ' ' not in s and len(re.findall(r'(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])', s)) >= 3:
                continue
            capsy = re.match(r'^[A-Z0-9][A-Z0-9 .,:;\-/\'"#()&+=%]*[A-Z0-9.)"\']$', s) and len(re.findall(r'[A-Z]', s)) >= 3
            ws = re.findall(r'[A-Za-z]+', s)
            wordsy = (' ' in s and len([w for w in ws if len(w) >= 2]) >= 2 and any(len(w) >= 4 for w in ws)
                      and not re.search(r'[a-z][A-Z]|[A-Za-z]\d[A-Za-z]', s)
                      and all(re.search(r'[AEIOUYaeiouy]', w) for w in ws if len(w) >= 4)
                      and sum(c.isalnum() or c == ' ' for c in s) / len(s) > 0.85
                      and sum(c in '<>{}*;:,/|\\^~`' for c in s) <= 2)
            if re.search(r'[bcdfghjklmnpqrstvwxzBCDFGHJKLMNPQRSTVWXZ]{5,}', s):
                continue
            plain = (re.match(r'^[A-Z]?[a-z]{4,}$', s) and re.search(r'[aeiou].*[aeiou]', s) and k == 0) \
                or (re.match(r'^[A-Z][a-z]+(?: [A-Z]?[a-z]+)+$', s) and len(s) >= 8)
            letters = [c for c in s if c.isalpha()]
            if len(letters) >= 6 and sum(c in 'fghijklmnoqr' for c in letters) / len(letters) > 0.7:
                continue
            if re.match(r'^\S{0,4}[ae]t [\-()+,/"*.]', s) or re.search(r'(.)\1\1', s):
                continue
            if capsy and not wordsy:
                vr = sum(c in 'AEIOU' for c in letters) / max(1, len(letters))
                if not (0.25 <= vr <= 0.75 and (len(s) >= 6 or re.search(r'[ \-.]', s))):
                    capsy = None
            if not (capsy or wordsy or plain):
                continue
            found.setdefault(s, m.start() + k)
    # drop strings that are mere substrings of longer ones
    keys = sorted(found, key=lambda x: found[x])
    longer = sorted(keys, key=len, reverse=True)
    keep = []
    for s in keys:
        if any(s != o and s in o for o in longer[:2000] if len(o) > len(s)):
            continue
        keep.append(s)
    pars = []
    if keep:
        pars.append({'heading': 'Text recovered from drawing (best effort)'})
        pars.extend(keep[:1500])
    s = f'AutoCAD DWG drawing, format {ver}' + (f' ({name})' if name else '') + '.'
    if keep:
        pref = [k for k in keep if ' ' in k and len(k) >= 8] + [k for k in keep if not (' ' in k and len(k) >= 8)]
        s += ' Recovered text includes: ' + _join([k[:60] for k in pref], 12) + '.'
    notes.append('DWG is a binary bit-packed format: text recovered heuristically; may be incomplete or contain fragments.')
    return _result('binary', type='AutoCAD DWG drawing', summary=s, paragraphs=pars, notes=notes,
                   meta=[('DWG version', f'{ver} {name}'.strip())])


def dwf(path, data):
    m = re.match(rb'\(DWF V(\d+)\.(\d+)\)', data)
    ver = f'{int(m.group(1))}.{int(m.group(2))}' if m else '?'
    pars, notes = [], []
    zi = data.find(b'PK\x03\x04')
    if zi >= 0:
        import zipfile
        try:
            z = zipfile.ZipFile(io.BytesIO(data[zi:]))
            names = z.namelist()
            pars.append({'heading': 'Package contents'}); pars.append('\n'.join(names[:300]))
            for n in names:
                if n.lower().endswith(('.xml', '.txt')) and z.getinfo(n).file_size < 2_000_000:
                    t = _dec(z.read(n))
                    vals = re.findall(r'(?:name|title|value|description)="([^"]{2,200})"', t, re.I)
                    txt = re.sub(r'<[^>]+>', ' ', t)
                    txt = re.sub(r'\s+', ' ', txt).strip()
                    if vals or txt:
                        pars.append({'heading': n})
                        if vals:
                            pars.append(', '.join(_uniq(vals)[:300]))
                        if txt:
                            pars.append(txt[:20000])
        except Exception as e:
            notes.append(f'Embedded package unreadable ({type(e).__name__}).')
    else:
        ss = _uniq(s for s in _strings(data[:8_000_000], 5) if _wordy(s, 5))
        if ss:
            pars.append({'heading': 'Readable strings'}); pars.append('\n'.join(ss[:400]))
    s = f'Autodesk DWF (Design Web Format) V{ver} published drawing.'
    return _result('binary', type='Autodesk DWF drawing', summary=s, paragraphs=pars, notes=notes,
                   meta=[('DWF version', ver)])


def step(path, data):
    text = _dec(data[:30_000_000])
    hdr = text[:text.find('ENDSEC')] if 'ENDSEC' in text else text[:20000]

    def strs(tag):
        m = re.search(tag + r'\s*\((.*?)\)\s*;', hdr, re.S)
        return [x.replace("''", "'").replace('\\\\', '\\') for x in re.findall(r"'((?:[^']|'')*)'", m.group(1))] if m else []
    fdesc = strs('FILE_DESCRIPTION')
    fname = strs('FILE_NAME')
    schema = strs('FILE_SCHEMA')
    prods = _uniq(re.findall(r"PRODUCT\s*\(\s*'((?:[^']|'')*)'\s*,\s*'((?:[^']|'')*)'", text))
    ents = collections.Counter(re.findall(r'^#\d+\s*=\s*([A-Z_0-9]+)\s*\(', text, re.M))
    pars = [{'heading': 'STEP header'}]
    if fdesc:
        pars.append('Description: ' + ' / '.join(x for x in fdesc if x))
    labels = ['Name', 'Timestamp', 'Author', 'Organization', 'Preprocessor', 'Originating system', 'Authorization']
    vals = fname
    meta = []
    if fname:
        pars.append(f'Name: {fname[0]}')
        if len(fname) > 1:
            pars.append(f'Timestamp: {fname[1]}')
        rest = fname[2:]
        if rest:
            pars.append('Author/organisation/system: ' + ' · '.join(x for x in rest if x))
        meta += [('File name', fname[0])] + ([('Timestamp', fname[1])] if len(fname) > 1 else [])
        if len(fname) >= 2:
            sysn = [x for x in fname[-3:] if x]
            if sysn:
                meta.append(('Originating system', ' · '.join(sysn)))
    if schema:
        pars.append('Schema: ' + ', '.join(schema)); meta.append(('Schema', ', '.join(schema)))
    if prods:
        pars.append({'heading': f'Products ({len(prods)})'})
        pars.extend(f'{a}' + (f' — {b}' if b and b != a else '') for a, b in prods)
    s = (f'STEP (ISO 10303-21) 3D model' + (f' "{fname[0]}"' if fname and fname[0] else '')
         + (f' with {len(prods)} product(s): ' + _join([a for a, _ in prods], 10) if prods else '')
         + f'; {sum(ents.values()):,} entities.')
    meta.append(('Entities', sum(ents.values())))
    return _result(type='STEP 3D model', summary=s, paragraphs=pars, meta=meta, keywords=[a for a, _ in prods[:8]])


def iges(path, data):
    text = _dec(data[:20_000_000])
    lines = text.splitlines()
    start = ' '.join(l[:72] for l in lines if len(l) > 72 and l[72] == 'S').strip()
    glob = ''.join(l[:72] for l in lines if len(l) > 72 and l[72] == 'G')
    gparts = re.findall(r'\d+H([^,;]*)', glob)
    pars = []
    if start:
        pars.append({'heading': 'Start section'}); pars.append(start)
    if gparts:
        pars.append({'heading': 'Global section strings'}); pars.extend(g for g in gparts if g.strip())
    s = 'IGES 3D/2D CAD exchange file' + (': ' + start[:200] if start else '') + '.'
    return _result(type='IGES CAD model', summary=s, paragraphs=pars)


def hpgl(path, data):
    text = _dec(data[:20_000_000])
    labels = [l.strip() for l in re.findall(r'LB([^\x03]*)\x03', text) if l.strip()]
    pens = len(set(re.findall(r'SP(\d+)', text)))
    pars = []
    if labels:
        pars.append({'heading': 'Plot labels'}); pars.extend(labels)
    s = f'HP-GL plot file ({pens} pens)' + (': labels ' + _join(_uniq(labels), 15) if labels else '') + '.'
    return _result(type='HP-GL plot file', summary=s, paragraphs=pars, meta=[('Labels', len(labels))])

# ---------------------------------------------------------------- CorelDRAW

CDR_VER = {b'CDR ': '3', b'CDR4': '4', b'CDR5': '5', b'CDR6': '6', b'CDR7': '7', b'CDR8': '8',
           b'CDR9': '9', b'CDRA': '10', b'CDRB': '11', b'CDRC': '12', b'CDRD': 'X3 (13)',
           b'CDRE': 'X4 (14)', b'CDRF': 'X5 (15)', b'CDRG': 'X6 (16)'}


def _cdr_pr(c):
    return c >= 0x20 and c != 0x7f or c in (9, 10, 13)


def _cdr_texts(u):
    out = []
    for m in re.finditer(rb'txtj', u):
        pos = m.start(); found = None
        for trail in (1, 2, 0):
            end = pos - trail
            for L in range(1, min(4000, end - 4)):
                st = end - L
                n = struct.unpack_from('<I', u, st - 4)[0]
                if n == L and all(_cdr_pr(c) for c in u[st:end]):
                    found = u[st:end].decode('cp1252', 'replace'); break
                if n * 2 == L:
                    try:
                        t = u[st:end].decode('utf-16le')
                        if all(c.isprintable() or c in '\r\n\t' for c in t):
                            found = t
                    except Exception:
                        pass
                    break
            if found:
                break
        if not found:
            e = pos
            while e > 0 and u[e - 1] == 0:
                e -= 1
            s = e
            while s > 0 and _cdr_pr(u[s - 1]) and e - s < 4000:
                s -= 1
            if e - s >= 1:
                found = u[s:e].decode('cp1252', 'replace')
        if found:
            out.append(found)
    if not out:
        for m in re.finditer(rb'txsm', u):
            sz = struct.unpack_from('<I', u, m.end())[0] if m.end() + 4 <= len(u) else 0
            t = _cdr5_txsm(u[m.end() + 4:m.end() + 4 + min(sz, 200000)])
            if t:
                out.append(t)
    return out


def _cdr5_txsm(ch):
    """CorelDRAW 5-8 'txsm': 8-byte glyph records [w:2][kern:2][char:2][flags:2]."""
    def ok(i):
        return ch[i + 5] == 0 and ch[i + 7] == 0 and 0 < ch[i + 6] < 0x40
    best, align = 0, 0
    for a in range(8):
        n = sum(1 for i in range(a, len(ch) - 7, 8) if ok(i))
        if n > best:
            best, align = n, a
    if not best:
        return ''
    run, cur = [], []
    for i in range(align, len(ch) - 7, 8):
        if ok(i):
            cur.append(ch[i + 4])
        else:
            if len(cur) > len(run):
                run = cur
            cur = []
    if len(cur) > len(run):
        run = cur
    txt = bytes(run).decode('cp1252', 'replace')
    segs = re.split(r'[\x00-\x0c\x0e-\x1f]+', txt)
    good = [x for x in segs if len(x.strip()) >= 2]
    if not good:
        good = [max(segs, key=len)] if segs else []
    return '\n'.join(x.replace('\r', '\n').strip() for x in good).strip()


CDR_JUNK16 = {'LastUsed', 'Isometric', 'ENU', 'Black', 'Guides', 'Style', 'Desktop', 'Layer 1', 'Grid', 'CommonBullets',
              'Arabic', 'CHINESE_BIG5', 'ArialMT', 'ArialUnicodeMS', 'Bullets', 'Western', 'Default Graphic',
              'Default Paragraph Text', 'Default Artistic Text', 'Page 1', 'White', 'Registration Color'}


def coreldraw(path, data):
    if data[:2] == b'PK':
        import zipfile
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            return _result('binary', type='CorelDRAW X4+ drawing (zip package)',
                           paragraphs=[{'heading': 'Package contents'}, '\n'.join(z.namelist()[:200])],
                           summary='CorelDRAW X4 or later drawing (zip-based package).')
        except Exception:
            pass
    if data[:4] != b'RIFF':
        return _binary_note(path, 'CorelDRAW file (unrecognised)', data)
    v = CDR_VER.get(data[8:12], data[8:12].decode('latin-1', 'replace'))
    us = []
    for m in re.finditer(rb'cmpr', data):
        k = data.find(b'CPng', m.start(), m.start() + 40)
        if k < 0:
            continue
        try:
            us.append(zlib.decompressobj().decompress(data[k + 8:], 200_000_000))
        except Exception:
            pass
    u = b''.join(us) if us else data
    texts = [t.replace('\r\n', '\n').replace('\r', '\n').strip() for t in _cdr_texts(u)]
    texts = [t for t in texts if t and t not in ('ENU', 'CASCADE') and not re.match(r'^[0-9a-f]{4,}$', t)
             and (len(t) <= 3 or sum(c.isalnum() or c.isspace() for c in t) / len(t) >= 0.6)]
    via16 = False
    if not texts:
        cand = []
        for src in (u, data) if us else (data,):
            for m in re.finditer(rb'(?:[\x20-\x7e]\x00){3,}', src):
                t = m.group().decode('utf-16le').strip()
                if len(t) >= 2 and re.search(r'[A-Za-z0-9]{2}', t) and t not in CDR_JUNK16 \
                        and not re.match(r'^(CorelDefault|Corel|Arial|Times|Tahoma|Symbol|Courier|Western|Default)', t) \
                        and '?' not in t and not t.startswith('C:\\') and not re.match(r'^[0-9a-f]{4,}$', t) \
                        and not re.search(r'-(Regular|Bold|Italic)$|^Wingdings|MT$| BT$', t):
                    cand.append(t)
        out16 = []
        for t in cand:
            if not out16 or out16[-1] != t:
                out16.append(t)
        texts, via16 = out16, bool(out16)
    fonts = _uniq(re.findall(r'[A-Z][A-Za-z ]{2,30}(?: BT| MT)?', ' '.join(
        m.decode('utf-16le', 'ignore') for m in re.findall(rb'font.{0,40}?((?:[A-Za-z ]\x00){3,})', u[:300000]))))[:10]
    pars = []
    if texts:
        pars.append({'heading': f'Text objects ({len(texts)})'})
        pars.extend(texts)
    ut = _uniq(t.replace('\n', ' ') for t in texts)
    ut = [t for t in ut if len(t) >= 4] + [t for t in ut if len(t) < 4]
    s = f'CorelDRAW {v} drawing'
    s += (' containing text: ' + _join([t[:60] for t in ut], 15) + '.') if ut else \
         ' (no text objects recovered; artwork may be converted to curves).'
    notes = [] if texts else ['No text objects recovered (text converted to curves, or format version not supported).']
    if via16:
        notes.append('Text recovered from UTF-16 strings in the file (object order not preserved).')
    return _result('document' if texts else 'binary', type=f'CorelDRAW {v} drawing', summary=s,
                   paragraphs=pars, notes=notes, meta=[('CorelDRAW version', v), ('Text objects', len(texts))])

# ---------------------------------------------------------------- non-EDA look-alikes

def dp2_deps(path, data):
    text = _dec(data).replace('\\\n', ' ')
    pars, targets, deps_all = [], [], []
    for l in text.splitlines():
        if ':' in l and not re.match(r'^[A-Za-z]:\\', l.strip()) or re.match(r'^\S+\.o\s*:', l):
            m = re.match(r'^\s*(\S+?\.\w+)\s*:\s*(.*)$', l)
            if m:
                deps = [d for d in re.split(r'\s+', m.group(2).strip()) if d]
                targets.append(m.group(1)); deps_all += deps
                pars.append(f'{m.group(1)} depends on: ' + (', '.join(deps) if deps else '(nothing)'))
                continue
        if l.strip():
            pars.append(l.strip())
    hdrs = _uniq(os.path.basename(d.replace('\\', '/')) for d in deps_all)
    s = ('Make dependency file (ImageCraft ICC compiler .dp2): ' + ', '.join(targets[:5])
         + (' depends on ' + _join(hdrs, 12) if hdrs else ' has no header dependencies') + '.')
    return _result('source', type='Compiler dependency list (.dp2)', summary=s, paragraphs=pars,
                   keywords=[os.path.splitext(t)[0] for t in targets[:3]] + hdrs[:8])


def xilinx_asy(path, data):
    text = _dec(data)
    names = re.findall(r'^SYMBOL\s+\S+\s+(\S+)', text, re.M)
    texts = re.findall(r'^TEXT\s+-?\d+\s+-?\d+\s+\w+\s+\d+\s+(.+)$', text, re.M)
    pins = re.findall(r'^PINATTR PinName (\S+)', text, re.M)
    pol = re.findall(r'^PINATTR Polarity (\S+)', text, re.M)
    rows = [f'{p} ({d})' if d else p for p, d in zip(pins, pol + [''] * len(pins))]
    title = texts[0].strip() if texts else ''
    pars = [{'heading': f'Pins ({len(pins)})'}, ', '.join(rows)]
    s = f'Xilinx ISE schematic symbol{" " + title if title else ""} with {len(pins)} pins: ' + _join(pins, 20) + '.'
    return _result('source', type='Xilinx ISE schematic symbol (.asy)', title=title, summary=s, paragraphs=pars,
                   keywords=[title] if title else [])


def xml_doc(path, data, typ=None):
    text = _dec(data)
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(text.encode('utf-8') if text.startswith('<?xml') and 'encoding' in text[:100] else text)
    except Exception:
        return _generic_text(path, typ or 'XML file', data)
    tags = collections.OrderedDict()
    attrs_of_interest = ('name', 'symbolname', 'entity_name', 'value', 'sof_file', 'jtag_device', 'device',
                         'family', 'type', 'title', 'id')
    texts = []
    for el in root.iter():
        tag = el.tag.split('}')[-1]
        vals = [el.attrib['name']] if 'name' in el.attrib else [el.attrib[a] for a in attrs_of_interest if a in el.attrib]
        if tag == 'instance' and 'symbolname' in el.attrib:
            vals = [f"{el.attrib.get('name', '')} ({el.attrib['symbolname']})"]
        if vals:
            tags.setdefault(tag, []).append(' '.join(vals) if len(vals) > 1 else vals[0])
        if el.text and el.text.strip():
            texts.append(el.text.strip())
    rtag = root.tag.split('}')[-1]
    if rtag == 'eagle':
        return eagle(path, root)
    if not typ:
        if rtag == 'session' and 'jtag_chain' in root.attrib:
            typ = 'Altera SignalTap II logic-analyser session'
        elif rtag == 'drawing' or 'schematic' in rtag.lower():
            typ = 'Xilinx ISE schematic (XML)'
        elif rtag == 'Network':
            typ = 'XMOS network/board description (.xn)'
        else:
            typ = f'XML document <{rtag}>'
    pars = []
    if root.attrib:
        pars.append({'heading': f'<{rtag}> attributes'})
        pars.append(', '.join(f'{k}={v}' for k, v in root.attrib.items()))
    for tag, vals in tags.items():
        uv = _uniq(vals)
        pars.append({'heading': f'{tag} ({len(uv)})'})
        pars.append(', '.join(uv[:2000]))
    if texts:
        pars.append({'heading': 'Text content'})
        pars.extend(_uniq(texts)[:2000])
    summ_bits = [f'{len(_uniq(v))} {t}' for t, v in list(tags.items())[:6]]
    s = typ + (': ' + ', '.join(summ_bits) if summ_bits else '') + '.'
    extra = [root.attrib.get(k) for k in ('sof_file', 'jtag_device') if root.attrib.get(k)]
    if extra:
        s += ' ' + '; '.join(extra) + '.'
    return _result('data', type=typ, summary=s, paragraphs=pars)


def eagle(path, root):
    ver = root.attrib.get('version', '')
    is_brd = root.find('.//board') is not None
    pars, meta = [], [('Eagle version', ver)]
    comps = []
    for el in root.iter('element'):
        comps.append((el.get('name', ''), el.get('value', ''), el.get('package', ''), el.get('library', '')))
    for el in root.iter('part'):
        comps.append((el.get('name', ''), el.get('value', '') or el.get('deviceset', ''), el.get('device', ''), el.get('library', '')))
    sigs = [el.get('name', '') for el in root.iter('signal')] + [el.get('name', '') for el in root.iter('net')]
    sigs = _uniq(s for s in sigs if s)
    texts = _uniq((el.text or '').strip() for el in root.iter('text') if (el.text or '').strip())
    descs = _uniq(re.sub(r'<[^>]+>', ' ', el.text or '').strip() for el in root.iter('description') if (el.text or '').strip())
    layers = [el.get('name', '') for el in root.iter('layer') if el.get('active') == 'yes']
    xs, ys = [], []
    plain = root.find('.//board/plain')
    if plain is not None:
        for w in plain.iter('wire'):
            if w.get('layer') == '20':
                for a in ('x1', 'x2'):
                    xs.append(float(w.get(a, 0)))
                for a in ('y1', 'y2'):
                    ys.append(float(w.get(a, 0)))
    size = (max(xs) - min(xs), max(ys) - min(ys)) if len(xs) > 1 else None
    comps.sort(key=lambda c: _natkey(c[0]))
    if comps:
        pars.append({'heading': f'Components ({len(comps)})'})
        pars.extend(' — '.join(x for x in (n, v, p and 'package ' + p, l and 'library ' + l) if x) for n, v, p, l in comps)
    if sigs:
        pars.append({'heading': f'Nets ({len(sigs)})'}); pars.append(', '.join(sigs))
    if texts:
        pars.append({'heading': 'Text'}); pars.extend(texts)
    if descs:
        pars.append({'heading': 'Descriptions'}); pars.extend(descs[:200])
    if layers:
        pars.append({'heading': 'Layers'}); pars.append(', '.join(layers))
    kind = 'board' if is_brd else 'schematic' if root.find('.//schematic') is not None else 'library'
    s = f'Eagle {ver} {kind}: {len(comps)} components, {len(sigs)} nets'
    if size:
        s += f', board outline {_fmt(size[0], 2)} x {_fmt(size[1], 2)} mm'
    s += '.'
    vals = _uniq(c[1] for c in comps if c[1])
    if vals:
        s += ' Parts include ' + _join(vals, 12) + '.'
    meta += [('Components', len(comps)), ('Nets', len(sigs))]
    return _result(type=f'Eagle {kind} (XML)', summary=s, paragraphs=pars, meta=meta, keywords=vals[:10])


def xilinx_sch_ascii(path, data):
    text = _dec(data)
    sigs = re.findall(r'^\s*SIGNAL (\S+)', text, re.M)
    insts = re.findall(r'^\s*BEGIN INSTANCE (\S+) (\S+)', text, re.M)
    iom = re.findall(r'^\s*IOMARKER [-\d ]+ (\S+)', text, re.M)
    fam = re.search(r'DeviceFamilyName "([^"]+)"', text)
    pars = []
    if insts:
        pars.append({'heading': f'Instances ({len(insts)})'})
        pars.extend(f'{b} — {a}' for a, b in insts)
    if sigs:
        pars.append({'heading': f'Signals ({len(_uniq(sigs))})'}); pars.append(', '.join(_uniq(sigs)))
    if iom:
        pars.append({'heading': 'I/O markers'}); pars.append(', '.join(_uniq(iom)))
    s = (f'Xilinx ECS schematic (ASCII){" for " + fam.group(1) if fam else ""}: {len(insts)} instances, '
         f'{len(_uniq(sigs))} signals.' + (' Symbols: ' + _join(_uniq(a for a, _ in insts), 12) + '.' if insts else ''))
    return _result('source', type='Xilinx ECS schematic (ASCII)', summary=s, paragraphs=pars)


def autoview_cam(path, data):
    text = _dec(data)
    files = [l.strip() for l in text.splitlines() if re.search(r'[\\/].+\.\w+$', l.strip())]
    s = 'Gerber viewer (Autoview) job listing ' + str(len(files)) + ' layer files: ' + _join(
        [os.path.basename(f.replace('\\', '/')) for f in files], 15) + '.'
    return _result(type='Gerber viewer job file (Autoview .cam)', summary=s, paragraphs=files)

# ---------------------------------------------------------------- dispatch

def _is_gerber(text):
    t = text[:200000]
    if re.search(r'%FS[LTD]?[AI]', t) or re.search(r'%MO(IN|MM)', t):
        return True
    if re.search(r'G0?4[ *]', t[:2000]) and re.search(r'%AD|D0?[123]\*|G54D\d+', t):
        return True
    if re.search(r'^\*?\s*G0?4', t[:200], re.M) and re.search(r'D0?[123]\*', t):
        return True
    return False


def _is_excellon(text):
    t = text[:20000]
    return bool(re.search(r'^M48\s*$', t, re.M) or (re.search(r'^T\d+C[\d.]+', t, re.M) and re.search(r'^X-?\d', t, re.M))
                or (t.lstrip().startswith('%') and re.search(r'^T\d+\s*$', t, re.M) and re.search(r'^X-?\d', t, re.M)))


def extract(path):
    try:
        r = _extract(path)
        if os.path.getsize(path) > MAXREAD and r.get('kind') != 'binary':
            r.setdefault('notes', []).append(f'File larger than {MAXREAD // 1_000_000} MB: only the first part was parsed.')
        return r
    except Exception as e:
        try:
            data = _read(path, 4_000_000)
            if _textish(data):
                r = _generic_text(path, 'Text file', data)
            else:
                r = _binary_note(path, 'Binary file', data)
            r.setdefault('notes', []).append(f'eda_cad parser failed ({type(e).__name__}: {str(e)[:100]}); generic extraction used.')
            return r
        except Exception:
            return {'kind': 'binary', 'notes': ['Unreadable file.']}


def _extract(path):
    name = os.path.basename(path)
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    size = os.path.getsize(path)
    if size == 0:
        return {'kind': 'binary', 'type': 'Empty file', 'notes': ['File is empty (0 bytes).'],
                'summary': f'Empty {ext.upper()} file (0 bytes).'}
    head = _read(path, 65536)
    # ---- containers
    if head.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        if ext in ('schdoc', 'schbak') or ext == 'sch':
            return altium_schdoc(path, head)
        if ext == 'schlib':
            return altium_schlib(path, head)
        if ext in ('pcbdoc', 'pcbbak', 'pcb'):
            return altium_pcbdoc(path, head)
        if ext == 'pcblib':
            return altium_pcblib(path, head)
        if ext == 'dsn':
            return orcad_dsn(path, head)
        o = _ole(path)
        try:
            names = ['/'.join(e) for e in o.listdir()]
        finally:
            o.close()
        if 'Board6/Data' in names:
            return altium_pcbdoc(path, head)
        if any(n.startswith('Views/') for n in names):
            return orcad_dsn(path, head)
        if 'FileHeader' in names:
            return altium_schdoc(path, head)
        o = _ole(path)
        try:
            return _ole_generic(path, o, 'OLE compound file')
        finally:
            o.close()
    if head.startswith(b'PK\x03\x04'):
        if ext == 'cdr':
            return coreldraw(path, _read(path))
        import zipfile
        try:
            z = zipfile.ZipFile(path)
            nm = z.namelist()
            return _result('binary', type=f'ZIP-packaged {ext.upper()} file', paragraphs=['\n'.join(nm[:300])],
                           summary=f'{ext.upper()} file stored as a ZIP package with {len(nm)} entries: ' + _join(nm, 10) + '.')
        except Exception:
            return _binary_note(path, f'{ext.upper()} file (zip)', head)
    if head.startswith(b'RIFF') and head[8:11] == b'CDR':
        return coreldraw(path, _read(path))
    if head.startswith(b'II') and (b'P-CAD' in head[:300] or b'ACCEL' in head[:300]):
        return pcad_binary(path, _read(path))
    if re.match(rb'AC\d{4}', head[:6]) or ext == 'dwg' and head[:2] == b'AC':
        return dwg(path, _read(path, 24_000_000))
    if head.startswith(b'(DWF V'):
        return dwf(path, _read(path))
    if not _textish(head):
        if ext == 'drl' and re.match(rb'T.{2}\x80', head[:4], re.S):
            r = _binary_note(path, 'Altium EIA binary NC drill file', head,
                             note='EIA RS-358 binary drill tape image; see the matching .DRR report for the tool table.',
                             strings=False)
            r['summary'] = ('NC drill tape in EIA RS-358 binary format (Altium output); no readable text. '
                            'The matching .DRR report lists tools and hole counts.')
            return r
        if head[:2] == b'\x1bE' or head[:1] == b'\x1b':
            return _binary_note(path, 'PCL/plotter print file', head, strings=False,
                                note='Printer-control (PCL/HP-GL/2) plot output; no extractable text.')
        if ext == 'cam':
            return _binary_note(path, 'Altium/CAMtastic CAM document (binary)', head)
        if ext in ('ddb', 'sxr'):
            return _binary_note(path, 'Altera Quartus database/report (binary)', head)
        if head[:512].count(0) == 512:
            r = _binary_note(path, f'Damaged {ext.upper()} file (zero-filled header)', _read(path, 8_000_000))
            r.setdefault('notes', []).insert(0, 'The first 512 bytes are all zero: the file header is missing '
                                                '(interrupted save or disk damage); only stray strings are recoverable.')
            return r
        if head.startswith(b';Tango'):
            r = _binary_note(path, 'Tango-PCB binary layout', _read(path, 8_000_000))
            r['summary'] = _dec(head[:60]).split('\n')[0].strip('; \r') + ' binary PCB layout; pattern/part names listed best-effort.'
            return r
        if ext == 'brd':
            r = _binary_note(path, 'Cadence Allegro / binary PCB board database', _read(path, 8_000_000))
            r.setdefault('notes', []).append('Proprietary binary board database: readable strings (net/part names) listed best-effort.')
            return r
        if ext == 'sch' and head[:2] == b'\x00\xfe':
            return _binary_note(path, 'PADS Logic binary schematic', _read(path, 8_000_000))
        return _binary_note(path, f'Binary {ext.upper()} file', _read(path, 8_000_000))
    # ---- text formats
    data = _read(path)
    t0 = _dec(data[:4000]).lstrip('﻿')
    ts = t0.lstrip()
    if ts.startswith('ACCEL_ASCII'):
        return accel_ascii(path, data)
    if ts.startswith(';Tango-PCB') or ts.startswith(';Tango'):
        return tango_pcb(path, data)
    if ts.startswith('[Preview]'):
        return altium_preview(path, data)
    if ts.startswith('[Design]'):
        return altium_prjpcb(path, data)
    if ts.startswith('[OutputJobFile]'):
        return altium_outjob(path, data)
    if ts.startswith('Record=') and ext.startswith('prjpcb'):
        return altium_structure(path, data)
    if ts.startswith('|HEADER=') or ts.startswith('|RECORD='):
        return altium_schdoc_ascii(path, data)
    if ts.startswith('Layer Pairs Export File'):
        return altium_pipe_report(path, data, 'Altium drill layer-pairs export (LDP)')
    if ts.startswith('DRC Rules Export File'):
        return altium_pipe_report(path, data, 'Altium DRC rules export (RUL)')
    if re.match(r'D\d+\s+[A-Z]', ts) and ext == 'apr' or ts.startswith('P-CAD Ap'):
        return aperture_report(path, data)
    if ts.startswith('ISO-10303-21'):
        return step(path, data)
    if ext in ('igs', 'iges') and len(t0) > 73:
        return iges(path, data)
    if re.match(r'(?s)\s*0\s*\n\s*(SECTION|EOF)', t0) or re.match(r'\s*999\s*\n', t0):
        return dxf(path, data)
    if ts.startswith('<'):
        return xml_doc(path, data)
    if ts.startswith('VERSION ') and 'BEGIN SCHEMATIC' in t0:
        return xilinx_sch_ascii(path, data)
    if ext == 'asy' and ts.startswith('Version') and 'SymbolType' in t0:
        return xilinx_asy(path, data)
    if re.match(r'(P-CAD|ACCEL) (Pick and Place|Bill of Materials)', ts) or ts.startswith('Bill of Material') \
            or (ext in ('pnp', 'bom') and ('---' in t0 or ts.startswith('"'))):
        return report_table(path, data)
    if (ts.startswith('P  ') or ts.startswith('C  ')) and re.search(r'^(317|327)', _dec(data[:400000]), re.M):
        return ipc356(path, data)
    if ext == 'ipc':
        return ipc356(path, data)
    text_full = None
    if ext not in ('dp2', 'schlog', 'schcmd', 'xn', 'drr', 'txt_drl'):
        text_full = _dec(data)
        if _is_gerber(text_full):
            return gerber(path, data)
        if _is_excellon(text_full):
            return excellon(path, data)
    if ts.startswith('[') and ext in ('net', 'netpreview', 'txt') or (ext == 'net' and re.match(r'\[\s*\n', ts)):
        return tango_netlist(path, data)
    if ext == 'dp2' or re.match(r'^\S+\.o\s*:', ts):
        return dp2_deps(path, data)
    if ext == 'plt' and re.search(r'\b(IN|SP\d|PU|PD)[;\d]', t0[:200]):
        return hpgl(path, data)
    if ext == 'cam' and re.match(r'(\d\s*\n){2,}', ts):
        return autoview_cam(path, data)
    if ext == 'drr':
        r = _generic_text(path, 'NC drill report', data)
        t = _dec(data)
        m = re.search(r'Totals\s+(\d+)', t)
        tools = len(re.findall(r'^T\d+\s', t, re.M))
        fm = re.search(r'For:\s*(.+?)\s{2,}', t)
        if m:
            r['summary'] = ('NC drill report' + (' for ' + fm.group(1) if fm else '')
                            + f': {tools} tools, {m.group(1)} holes.')
        return r
    typ = {'sxr': 'Synthesis cross-reference report (SXR)', 'schlog': 'Xilinx ECS schematic editor log', 'schcmd': 'Xilinx ECS schematic command script',
           'annotation': 'Altium annotation file', 'ldp': 'Altium layer-pairs file', 'rul': 'Rules export',
           'net': 'Netlist (text)', 'bom': 'Bill of materials (text)', 'pnp': 'Pick-and-place (text)'}.get(ext, f'{ext.upper()} text file')
    return _generic_text(path, typ, data)
