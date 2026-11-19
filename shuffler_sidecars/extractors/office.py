"""Office documents and spreadsheets.

Word (.doc/.dot/.wbk via catdoc, .docx/.docm XML), RTF (own stripper),
WordPerfect 5/6+ (.wpd, own best-effort decoder), PowerPoint (.ppt via
catppt, .pptx XML), Excel (.xls via xlrd, .xlsx/.xlsm via openpyxl), CSV,
SYLK (.slk), Outlook .msg (olefile), Access .mdb (own Jet3/Jet4 reader),
OpenDocument (.odt/.ods), Works (.wps).

Formats are sniffed from the file's magic bytes, not trusted from the
extension: in this archive many .xls are really xlsx, some .doc are RTF or
WordPerfect, .slk are Gerber silkscreen layers, .dot are Graphviz graphs and
.msg are Synplify log files.
"""
import os, re, io, csv, zipfile, struct, datetime, subprocess, collections
import xml.etree.ElementTree as ET

import core

EXTS = {'doc', 'dot', 'docx', 'docm', 'rtf', 'wpd', 'wp6', 'wbk', 'ppt', 'pptx', 'xls', 'xlsx',
        'xlsm', 'csv', 'slk', 'msg', 'mdb', 'wps', 'odt', 'ods'}

MAX_ROWS = 2000          # rows per sheet / table written to the sidecar
MAX_CELL = 2000          # characters per cell
SUB_TIMEOUT = 60

# ------------------------------------------------------------------ helpers

def _clean(s):
    s = s.replace('\r\n', '\n').replace('\r', '\n').replace('\x0b', '\n')
    s = re.sub(r'[\x00-\x08\x0c\x0e-\x1f\x7f]', '', s)
    return s


def _cell(v):
    """Render a spreadsheet cell value as text."""
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'TRUE' if v else 'FALSE'
    if isinstance(v, float):
        if v != v:
            return ''
        if v.is_integer() and abs(v) < 1e15:
            return str(int(v))
        return ('%.10g' % v)
    if isinstance(v, datetime.datetime):
        if v.hour == v.minute == v.second == 0:
            return v.strftime('%Y-%m-%d')
        return v.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(v, (datetime.date, datetime.time)):
        return v.isoformat()
    s = _clean(str(v)).strip().replace('\n', ' / ')
    if len(s) > MAX_CELL:
        s = s[:MAX_CELL] + ' …'
    return s


def _row(cells):
    """Join cells with ' | ', dropping trailing empties. Returns '' for empty rows."""
    vals = [_cell(c) for c in cells]
    while vals and not vals[-1]:
        vals.pop()
    if not any(vals):
        return ''
    return ' | '.join(vals)


_PN = re.compile(r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9][A-Za-z0-9\-_/\.#]{3,30}$')
_NOT_PN = re.compile(r'^([0-9A-Fa-f]{6}|0x[0-9A-Fa-f]+|\d+(\.\d+)?(mil|mm|in|uf|nf|pf|k|r|m|v|ohm|%)?|[A-Z]{1,3}\d{1,4}|ISS\d+|REV\w*|R\d+C\d+)$', re.I)


def _partnos(rows_text, n=10):
    """Part-number-like cell values (letters+digits, not designators / plain values), most frequent first."""
    cnt, first = collections.Counter(), {}
    for r in rows_text:
        for c in r.split(' | '):
            c = c.strip()
            if _PN.match(c) and not _NOT_PN.match(c):
                cnt[c] += 1
                first.setdefault(c, len(first))
    return sorted(cnt, key=lambda k: (-cnt[k], first[k]))[:n]


def _table_rows(rows_iter, limit=MAX_ROWS):
    """Cell lists -> (row texts, truncated, all_empty_columns_dropped).

    Columns empty in every kept row are removed (keeps alignment with the header
    but drops spacer columns); trailing empties are trimmed."""
    buf, trunc = [], False
    for cells in rows_iter:
        vals = [_cell(c) for c in cells]
        if not any(vals):
            continue
        if len(buf) >= limit:
            trunc = True
            break
        buf.append(vals)
    width = max((len(v) for v in buf), default=0)
    used = [any(i < len(v) and v[i] for v in buf) for i in range(width)]
    out = []
    for v in buf:
        v = [x for i, x in enumerate(v) if used[i]]
        while v and not v[-1]:
            v.pop()
        out.append(' | '.join(v))
    return out, trunc, sum(used)


def _run(cmd, path):
    try:
        p = subprocess.run(cmd + [path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=SUB_TIMEOUT, stdin=subprocess.DEVNULL)
        return p.stdout.decode('utf-8', 'replace')
    except Exception:
        return None


def _dt(v):
    if isinstance(v, datetime.datetime):
        return v.strftime('%Y-%m-%d %H:%M')
    return str(v)


def _ole_meta(path):
    """Summary-information properties of an OLE2 compound file."""
    meta, title = [], ''
    try:
        import olefile
        with olefile.OleFileIO(path) as ole:
            m = ole.get_metadata()
        def g(a):
            v = getattr(m, a, None)
            if isinstance(v, bytes):
                v = v.decode('cp1252', 'replace')
            if isinstance(v, str):
                v = _clean(v).strip()
            return v
        title = g('title') or ''
        for lab, a in (('Title', 'title'), ('Subject', 'subject'), ('Author', 'author'),
                       ('Last saved by', 'last_saved_by'), ('Company', 'company'),
                       ('Created', 'create_time'), ('Last saved', 'last_saved_time'),
                       ('Revision', 'revision_number'), ('Pages', 'num_pages'),
                       ('Words', 'num_words'), ('Application', 'creating_application'),
                       ('Template', 'template'), ('Comments', 'comments')):
            v = g(a)
            if v in (None, '', 0) or (isinstance(v, datetime.datetime) and v.year < 1980):
                continue
            meta.append((lab, _dt(v)))
    except Exception:
        pass
    return meta, title


def _sniff(path):
    with open(path, 'rb') as f:
        head = f.read(2048)
    if head[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':
        return 'ole'
    if head[:4] == b'PK\x03\x04':
        return 'zip'
    if head[:5] == b'{\\rtf':
        return 'rtf'
    if head[:4] == b'\xffWPC':
        return 'wpc'
    if head[4:19] in (b'Standard Jet DB', b'Standard ACE DB'):
        return 'jet'
    if head[:3] == b'ID;':
        return 'sylk'
    if re.match(rb'\s*(G0?4|%FS|%MO|\*%FS)', head):
        return 'gerber'
    if not head:
        return 'empty'
    return 'other'

# ------------------------------------------------------------------ dispatcher

def extract(path):
    ext = path.rsplit('.', 1)[-1].lower() if '.' in os.path.basename(path) else ''
    try:
        kind = _sniff(path)
    except Exception as e:
        return {'kind': 'binary', 'notes': [f'Could not read file: {e}']}
    try:
        if kind == 'empty':
            return {'kind': 'binary', 'type': 'Empty file', 'notes': ['File is empty (0 bytes).']}
        if kind == 'ole':
            return _ole(path, ext)
        if kind == 'zip':
            return _zip(path, ext)
        if kind == 'rtf':
            r = _rtf(path)
            if ext not in ('rtf',):
                r.setdefault('notes', []).append(f'File has a .{ext} extension but is RTF.')
            return r
        if kind == 'wpc':
            return _wpd(path)
        if kind == 'jet':
            return _mdb(path)
        if kind == 'sylk':
            return _sylk(path)
        if kind == 'gerber':
            return _gerber(path)
        # plain text / unknown binary
        if ext == 'dot' and not core.looks_binary(path):
            return _graphviz(path)
        if ext == 'csv' and not core.looks_binary(path):
            return _csv(path)
        if ext == 'msg' and not core.looks_binary(path):
            return _textlog(path, 'Synthesis tool message log (text, not an Outlook message)')
        if not core.looks_binary(path):
            return _textlog(path, f'Plain text file with .{ext} extension')
        return _strings(path, f'Unrecognised binary .{ext} file')
    except Exception as e:
        try:
            r = _strings(path, f'.{ext} file')
        except Exception:
            r = {'kind': 'binary'}
        r.setdefault('notes', []).append(f'Structured {kind} extraction failed ({type(e).__name__}: {str(e)[:150]}); readable strings shown instead.')
        return r

# ------------------------------------------------------------------ generic text / strings

def _textlog(path, typ):
    text, trunc = core.read_text(path, 5_000_000)
    r = {'kind': 'document', 'type': typ, 'paragraphs': core.split_paragraphs(_clean(text))}
    if trunc:
        r['notes'] = ['Text truncated at 5 MB.']
    return r


def _strings_from(data, minlen=5):
    out = []
    for m in re.finditer(rb'[\x20-\x7e\x91-\x97\xa0-\xff\t]{%d,}' % minlen, data):
        s = m.group(0).decode('cp1252', 'replace').strip()
        if sum(c.isalpha() for c in s) >= max(3, len(s) * 0.4):
            out.append(s)
    for m in re.finditer(rb'(?:[\x20-\x7e]\x00){%d,}' % minlen, data):
        s = m.group(0).decode('utf-16-le', 'replace').strip()
        if sum(c.isalpha() for c in s) >= max(3, len(s) * 0.4):
            out.append(s)
    return out


def _strings(path, typ):
    with open(path, 'rb') as f:
        data = f.read(20_000_000)
    pars, seen = [], set()
    for s in _strings_from(data, 6):
        if s not in seen:
            seen.add(s); pars.append(s)
        if len(pars) > 5000:
            break
    zeros = data.count(0) / max(1, len(data))
    if not pars and zeros > 0.9:
        return {'kind': 'binary', 'type': typ, 'meta': [('Zero bytes', f'{zeros:.0%}')],
                'notes': ['File content is (almost) entirely zero bytes: damaged or blanked file, no text recoverable.']}
    return {'kind': 'binary', 'type': typ, 'paragraphs': pars,
            'notes': ['No structured parser for this content: readable text strings extracted from the binary (best effort).']}

# ------------------------------------------------------------------ OLE2 (doc, xls, ppt, msg, wps)

def _ole(path, ext):
    import olefile
    with olefile.OleFileIO(path) as ole:
        streams = ['/'.join(s) for s in ole.listdir(streams=True, storages=False)]
    low = {s.lower() for s in streams}
    meta, title = _ole_meta(path)
    expect = None
    if 'worddocument' in low:
        r = _word97(path, ext); expect = ('doc', 'dot', 'wbk')
    elif 'workbook' in low or 'book' in low:
        r = _xls(path); expect = ('xls',)
    elif 'powerpoint document' in low:
        r = _ppt(path); expect = ('ppt',)
    elif any(s.startswith('__substg1.0_') for s in low):
        r = _msg(path)
    elif 'contents' in low and ext == 'wps':
        r = _strings(path, 'Microsoft Works document')
    else:
        r = _strings(path, f'OLE2 compound file (.{ext})')
        r['outline'] = [{'heading': 'OLE streams'}] + streams[:200]
    if expect and ext not in expect:
        r.setdefault('notes', []).append(f'File has a .{ext} extension but is a {r.get("type", "different format")}.')
    r['meta'] = meta + (r.get('meta') or [])
    if title and not r.get('title'):
        r['title'] = title
    return r


_FLD_ARG = r'(?:"[^"]*"|[^\s\\"]+)'
_FIELD = re.compile(r'\s?\b(?:PAGEREF|SEQ|TOC|HYPERLINK|REF|NOTEREF|DATE|TIME|SUBJECT|TITLE|NUMPAGES|PAGE|SECTIONPAGES|'
                    r'STYLEREF|INCLUDEPICTURE|INCLUDETEXT|EMBED|FILENAME|DOCPROPERTY|AUTHOR|SAVEDATE|PRINTDATE|'
                    r'CREATEDATE|LINK|FORMTEXT|FORMCHECKBOX|MACROBUTTON|XE|TC|LISTNUM|QUOTE|SET|ASK|FILLIN|IF|INDEX|COMMENTS|KEYWORDS)'
                    r'(?:\s+(?!\\)' + _FLD_ARG + r'){0,3}(?:\s*(?:\\[*@#fols]\s*' + _FLD_ARG + r'|\\[a-zA-Z!]))+\s?')
_HYPER = re.compile(r'HYPERLINK\s+(?:\\l\s+)?"[^"]*"(?:\s*\\[a-z](?:\s*"[^"]*")?)*\s?')
_SYMFLD = re.compile(r'SYMBOL\s+(\d+)(?:\s*\\[a-z]\s*(?:"[^"]*"|\d+)?)*\s*\|?')
_SYMCH = {183: '•', 167: '§', 168: '♣', 216: '⌀', 176: '°', 177: '±', 179: '≥', 163: '≤', 180: '×', 87: 'Ω', 109: 'µ', 252: '✓'}


def _strip_fields(t):
    t = _SYMFLD.sub(lambda m: _SYMCH.get(int(m.group(1)), '•') + ' ', t)
    t = _FIELD.sub(' ', t)
    t = _HYPER.sub('', t)
    return re.sub(r'[ \xa0]{2,}', ' ', t).strip()


def _word97(path, ext):
    txt = _run(['catdoc', '-w', '-d', 'utf-8'], path)
    typ = {'dot': 'Microsoft Word template', 'wbk': 'Microsoft Word backup document'}.get(ext, 'Microsoft Word document')
    if txt is None:
        return _strings(path, typ + ' (catdoc failed)')
    pars = []
    for ln in _clean(txt).split('\n'):
        ln = _strip_fields(ln.rstrip()) if ('\\' in ln or 'SYMBOL' in ln or 'HYPERLINK' in ln) else ln.rstrip()
        if not ln.strip():
            continue
        fields = [f.strip() for f in ln.split('\t')]
        nonempty = [f for f in fields if f]
        if len(nonempty) >= 2:
            ln = ' | '.join(nonempty)
        else:
            ln = ln.replace('\t', ' ').strip()
        pars.append(ln)
    r = {'kind': 'document', 'type': typ + ' (Word 97-2003)', 'paragraphs': pars}
    if not pars:
        r['notes'] = ['No text found in this document (probably images or embedded objects only).']
    return r


def _ppt_texts(stream, off, end, out, skip_masters=True):
    """Collect (texttype, text) from text atoms inside [off, end)."""
    tt = None
    while off + 8 <= end:
        verinst, rtype, rlen = struct.unpack_from('<HHI', stream, off)
        body, nxt = off + 8, off + 8 + rlen
        if nxt > end:
            break
        if verinst & 0xF == 0xF:
            if rtype not in (0x1388, 0x07E4, 0x0FF5, 0x03F0, 0x03F8):   # prog tags, sound, VBA, notes, master
                _ppt_texts(stream, body, nxt, out)
        elif rtype == 0x0F9F and rlen >= 4:
            tt = struct.unpack_from('<I', stream, body)[0]
        elif rtype in (0x0FA0, 0x0FA8):
            raw = stream[body:nxt]
            t = raw.decode('utf-16-le', 'replace') if rtype == 0x0FA0 else raw.decode('cp1252', 'replace')
            t = _clean(t.replace('\r', '\n')).strip()
            if t and t != '*':
                out.append((tt, t))
            tt = None
        off = nxt


def _ppt_slides(ole):
    """Current slides in order via CurrentUser -> UserEditAtom chain -> persist directory."""
    stream = ole.openstream('PowerPoint Document').read()
    cu = ole.openstream('Current User').read()
    edit = struct.unpack_from('<I', cu, 16)[0]
    persist, guard, doc_ref = {}, 0, None
    while edit and edit + 8 <= len(stream) and guard < 500:
        guard += 1
        _, rtype, rlen = struct.unpack_from('<HHI', stream, edit)
        if rtype != 0x0FF5:
            break
        body = edit + 8
        last, pdir, dref = struct.unpack_from('<III', stream, body + 8)
        if doc_ref is None:
            doc_ref = dref
        _, prt, plen = struct.unpack_from('<HHI', stream, pdir)
        o, e = pdir + 8, pdir + 8 + plen
        while o + 4 <= e:
            v = struct.unpack_from('<I', stream, o)[0]
            pid, cnt = v & 0xFFFFF, v >> 20
            o += 4
            for k in range(cnt):
                if o + 4 > e:
                    break
                persist.setdefault(pid + k, struct.unpack_from('<I', stream, o)[0])
                o += 4
        if last == edit:
            break
        edit = last
    doc = persist.get(doc_ref)
    if doc is None:
        raise ValueError('no document container')
    _, dt, dlen = struct.unpack_from('<HHI', stream, doc)
    slides = []          # [persist_ref, slwt_texts]
    def walk(off, end):
        while off + 8 <= end:
            verinst, rtype, rlen = struct.unpack_from('<HHI', stream, off)
            body, nxt = off + 8, off + 8 + rlen
            if nxt > end:
                break
            if rtype == 0x0FF0 and verinst >> 4 == 0:      # SlideListWithText for slides
                o, tt = body, None
                while o + 8 <= nxt:
                    vi, rt, rl = struct.unpack_from('<HHI', stream, o)
                    if rt == 0x03F3:
                        slides.append([struct.unpack_from('<I', stream, o + 8)[0], []])
                    elif rt == 0x0F9F and rl >= 4:
                        tt = struct.unpack_from('<I', stream, o + 8)[0]
                    elif rt in (0x0FA0, 0x0FA8) and slides:
                        raw = stream[o + 8:o + 8 + rl]
                        t = raw.decode('utf-16-le', 'replace') if rt == 0x0FA0 else raw.decode('cp1252', 'replace')
                        t = _clean(t.replace('\r', '\n')).strip()
                        if t and t != '*':
                            slides[-1][1].append((tt, t))
                        tt = None
                    o += 8 + rl
            elif verinst & 0xF == 0xF and rtype not in (0x0FF0,):
                walk(body, nxt)
            off = nxt
    walk(doc + 8, doc + 8 + dlen)
    out = []
    for ref, slwt in slides:
        texts = []
        so = persist.get(ref)
        if so is not None and so + 8 <= len(stream):
            _, st, sl = struct.unpack_from('<HHI', stream, so)
            if st == 0x03EE:
                _ppt_texts(stream, so + 8, so + 8 + sl, texts)
        have = {t for _, t in texts}
        texts += [x for x in slwt if x[1] not in have]
        out.append(texts)
    return out


def _ppt(path):
    import olefile
    slides = None
    try:
        with olefile.OleFileIO(path) as ole:
            slides = _ppt_slides(ole)
    except Exception:
        slides = None
    pars, n = [], 0
    if slides is not None:
        for sl in slides:
            if not sl:
                n += 1
                pars.append({'heading': f'Slide {n}'})
                continue
            n += 1
            title = next((t for tt, t in sl if tt in (0, 6)), '')
            pars.append({'heading': f'Slide {n}' + (f': {re.sub(r"\s+", " ", title)[:120]}' if title else '')})
            for tt, t in sl:
                if t == title:
                    continue
                pars.extend(x.strip() for x in t.split('\n') if x.strip())
    else:
        txt = _run(['catppt', '-d', 'utf-8'], path)
        if txt is None:
            return _strings(path, 'Microsoft PowerPoint presentation')
        for sl in _clean(txt.replace('\f', '\x00SLIDE\x00')).split('SLIDE'):
            lines = [l.strip() for l in sl.split('\n') if l.strip()
                     and not re.match(r'^(Office Theme|Default Design|Click to edit .*|\*|‹#›)$', l.strip())]
            if not lines:
                continue
            n += 1
            pars.append({'heading': f'Slide {n}: {lines[0][:100]}'})
            pars.extend(lines[1:])
    withtext = sum(1 for p in pars if isinstance(p, str))
    r = {'kind': 'document', 'type': 'Microsoft PowerPoint presentation (97-2003)', 'paragraphs': pars,
         'meta': [('Slides', n)], 'summary': _deck_summary(pars)}
    if not withtext and not any(': ' in p['heading'] for p in pars):
        r['notes'] = ['No slide text found (presentation is probably drawings/images only).']
    return r


def _msg(path):
    import olefile
    with olefile.OleFileIO(path) as ole:
        def prop(code):
            for suf, enc in (('001F', 'utf-16-le'), ('001E', 'cp1252')):
                nm = f'__substg1.0_{code}{suf}'
                if ole.exists(nm):
                    return _clean(ole.openstream(nm).read().decode(enc, 'replace')).rstrip('\x00').strip()
            return ''
        subj, frm, frm_e = prop('0037'), prop('0C1A'), prop('0C1F') or prop('5D01')
        to, cc, body = prop('0E04'), prop('0E03'), prop('1000')
        hdrs = prop('007D')
        atts = []
        for e in ole.listdir(streams=True, storages=False):
            if e[0].startswith('__attach_version1.0_') and len(e) == 2 and e[1][:16] in ('__substg1.0_3707', '__substg1.0_3704'):
                try:
                    atts.append(_clean(ole.openstream(e).read().decode('utf-16-le' if e[1].endswith('1F') else 'cp1252', 'replace')).strip('\x00 '))
                except Exception:
                    pass
    date = ''
    m = re.search(r'^Date:\s*(.+)$', hdrs, re.M)
    if m:
        date = m.group(1).strip()
    meta = [(k, v) for k, v in (('Subject', subj), ('From', f'{frm} <{frm_e}>' if frm_e else frm),
                                 ('To', to), ('Cc', cc), ('Date', date),
                                 ('Attachments', ', '.join(sorted(set(atts))))) if v]
    pars = core.split_paragraphs(body) if body else []
    return {'kind': 'document', 'type': 'Outlook e-mail message', 'title': subj, 'meta': meta,
            'paragraphs': pars, 'keywords': [subj] if subj and len(subj) < 60 else []}

# ------------------------------------------------------------------ spreadsheets

def _sheet_block(name, rows_iter, total_rows=None, label='Sheet'):
    """rows_iter yields lists of cell values. Returns (paragraphs, row texts, truncated, info)."""
    texts, trunc, ncols = _table_rows(rows_iter)
    pars = [{'heading': f'{label}: {name}'}] + texts
    if not texts:
        pars.append('(empty)')
    if trunc:
        pars.append(f'… truncated: first {MAX_ROWS:,} non-empty rows shown'
                    + (f' of {total_rows:,} rows.' if total_rows else '.'))
    info = {'name': name, 'rows': len(texts), 'cols': ncols, 'first': texts[:3], 'total': total_rows}
    return pars, texts, trunc, info


def _data_summary(what, infos, label='sheet'):
    parts = []
    nonempty = [i for i in infos if i['rows']]
    for k, i in enumerate(nonempty[:8]):
        rows = i['total'] if i['total'] and i['total'] > i['rows'] else i['rows']
        if k < 3:
            first = ' / '.join(' | '.join(c for c in t.split(' | ') if c.strip())[:90] for t in i['first'][:2])
            parts.append(f"'{i['name']}' ({rows:,} rows × {i['cols']} columns; begins: {first})")
        else:
            parts.append(f"'{i['name']}' ({rows:,} rows)")
    s = f"{what} with {len(infos)} {label}{'s' if len(infos) != 1 else ''}"
    if len(nonempty) < len(infos):
        s += f" ({len(infos) - len(nonempty)} empty)"
    if parts:
        s += ': ' + '; '.join(parts)
    if len(nonempty) > 8:
        s += f'; and {len(nonempty) - 8} more'
    return s[:1500] + '.'


def _finish_sheets(r, all_texts, sheet_meta, truncated, infos=None, what='Spreadsheet'):
    r['meta'] = (r.get('meta') or []) + [('Sheets', len(sheet_meta)),
                                         ('Sheet list', '; '.join(sheet_meta))]
    kw = _partnos(all_texts)
    if kw:
        r['keywords'] = kw
    if infos is not None:
        r['summary'] = _data_summary(what, infos)
    if truncated:
        r.setdefault('notes', []).append(f'Large sheet(s) truncated to the first {MAX_ROWS:,} non-empty rows: ' + ', '.join(truncated))
    return r


def _xls(path):
    import xlrd
    try:
        bk = xlrd.open_workbook(path, on_demand=True, formatting_info=False, logfile=io.StringIO())
    except Exception as e:
        r = _strings(path, 'Microsoft Excel workbook (97-2003)')
        if 'encrypt' in str(e).lower():
            r = {'kind': 'binary', 'type': 'Microsoft Excel workbook (97-2003), encrypted',
                 'notes': ['Workbook is encrypted / password-protected: cell contents cannot be read.']}
        else:
            r.setdefault('notes', []).append(f'xlrd could not open the workbook ({str(e)[:120]}).')
        return r
    pars, alltexts, smeta, truncs, infos = [], [], [], [], []
    try:
        for i in range(bk.nsheets):
            sh = bk.sheet_by_index(i)
            def rows(sh=sh):
                for rx in range(sh.nrows):
                    out = []
                    for c in sh.row(rx):
                        if c.ctype == xlrd.XL_CELL_DATE:
                            try:
                                out.append(xlrd.xldate.xldate_as_datetime(c.value, bk.datemode))
                            except Exception:
                                out.append(c.value)
                        elif c.ctype == xlrd.XL_CELL_ERROR:
                            out.append(xlrd.error_text_from_code.get(c.value, '#ERR'))
                        elif c.ctype == xlrd.XL_CELL_BOOLEAN:
                            out.append(bool(c.value))
                        else:
                            out.append(c.value)
                    yield out
            p, t, tr, inf = _sheet_block(sh.name, rows(), sh.nrows)
            pars += p; alltexts += t; infos.append(inf)
            smeta.append(f'{sh.name} ({sh.nrows}×{sh.ncols})')
            if tr:
                truncs.append(sh.name)
            bk.unload_sheet(i)
    finally:
        bk.release_resources()
    r = {'kind': 'data', 'type': f'Microsoft Excel workbook (BIFF{bk.biff_version // 10 if bk.biff_version >= 20 else bk.biff_version})',
         'paragraphs': pars}
    if bk.user_name:
        r['meta'] = [('Last user', bk.user_name)]
    return _finish_sheets(r, alltexts, smeta, truncs, infos, 'Excel workbook')


def _xlsx(path, z):
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return _xlsx2(path)


def _xlsx2(path):
    import openpyxl
    if True:
        fh = open(path, 'rb')   # file object: openpyxl rejects a .xls *name* even when content is xlsx
        wb = openpyxl.load_workbook(fh, read_only=True, data_only=True, keep_links=False)
    pars, alltexts, smeta, truncs, infos = [], [], [], [], []
    try:
        for ws in wb.worksheets:
            try:
                dims = ws.calculate_dimension()
            except Exception:
                dims = '?'
            mr = ws.max_row
            p, t, tr, inf = _sheet_block(ws.title, ws.iter_rows(values_only=True), mr)
            pars += p; alltexts += t; infos.append(inf)
            smeta.append(f'{ws.title} ({dims})')
            if tr:
                truncs.append(ws.title)
        for cs in getattr(wb, 'chartsheets', []):
            smeta.append(f'{cs.title} (chart sheet)')
    finally:
        wb.close(); fh.close()
    r = {'kind': 'data', 'type': 'Microsoft Excel workbook (Office Open XML)', 'paragraphs': pars}
    return _finish_sheets(r, alltexts, smeta, truncs, infos, 'Excel workbook')


def _csv(path):
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        raw = f.read(65536)
    enc = 'utf-8-sig'
    try:
        raw.decode('utf-8')
    except UnicodeDecodeError:
        enc = 'cp1252'
    sample = raw.decode(enc, 'replace')
    try:
        dialect = csv.Sniffer().sniff(sample[:20000], delimiters=',;\t|')
    except Exception:
        dialect = csv.excel
    comments, counter = [], [0]
    def gen(rd):
        try:
            for row in rd:
                counter[0] += 1
                if len(row) == 1 and row[0].lstrip().startswith('#'):
                    t = row[0].lstrip('# ').strip()
                    if t and len(comments) < 200:
                        comments.append(t)
                    continue
                yield row
        except csv.Error:
            return
    with open(path, encoding=enc, errors='replace', newline='') as f:
        rd = csv.reader(f, dialect)
        texts, trunc, ncols = _table_rows(gen(rd))
        if trunc:   # count the remaining lines cheaply
            for _ in f:
                counter[0] += 1
    total = counter[0]
    pars = comments + texts
    head = texts[0] if texts else ''
    r = {'kind': 'data', 'type': 'Comma-separated values table', 'paragraphs': pars,
         'meta': [('Rows', f'{total:,}'), ('Delimiter', repr(getattr(dialect, 'delimiter', ',')))]}
    if head:
        r['meta'].append(('Header row', head[:300]))
        cols = [c.strip().lower() for c in head.split(' | ')]
        if 'designator' in cols and any('x' in c for c in cols):
            r['type'] = 'Pick-and-place (component placement) table, CSV'
        elif {'designator', 'comment'} & set(cols) and 'footprint' in cols:
            r['type'] = 'Bill of materials, CSV'
    if trunc:
        r['notes'] = [f'Large table: first {MAX_ROWS:,} non-empty rows of about {total:,} lines shown.']
    r['summary'] = (f"{r['type']}: {total:,} rows × {ncols} columns"
                    + (f"; header: {head[:300]}" if head else '')
                    + (f"; second row: {texts[1][:200]}" if len(texts) > 1 else '')
                    + (f". Leading comments: {'; '.join(comments[:3])[:300]}" if comments else '') + '.')
    kw = _partnos(texts)
    if kw:
        r['keywords'] = kw
    return r


def _sylk(path):
    text, _ = core.read_text(path, 20_000_000)
    cells = collections.defaultdict(dict)
    cx = cy = 1
    for ln in text.splitlines():
        parts = ln.split(';')
        if parts[0] not in ('C', 'F'):
            continue
        val = None
        for p in parts[1:]:
            if p[:1] == 'X':
                cx = int(p[1:] or cx)
            elif p[:1] == 'Y':
                cy = int(p[1:] or cy)
            elif p[:1] == 'K' and parts[0] == 'C':
                val = p[1:]
                if val.startswith('"') and val.endswith('"'):
                    val = val[1:-1].replace('""', '"')
        if val is not None:
            cells[cy][cx] = val
    def rows():
        for y in sorted(cells):
            row = cells[y]
            yield [row.get(x, '') for x in range(1, max(row) + 1)]
    p, t, tr, inf = _sheet_block('SYLK', rows(), len(cells))
    r = {'kind': 'data', 'type': 'SYLK spreadsheet', 'paragraphs': p}
    return _finish_sheets(r, t, ['SYLK'], ['SYLK'] if tr else [], [inf], 'SYLK spreadsheet')


def _gerber(path):
    text, _ = core.read_text(path, 30_000_000)
    comments, aps = [], []
    units = fmt = ''
    draws = flashes = 0
    for m in re.finditer(r'G0?4\s*([^*]*)\*', text):
        c = m.group(1).strip()
        if c:
            comments.append(c)
    for m in re.finditer(r'%ADD(\d+)([^*%]*)\*%', text):
        aps.append(f'D{m.group(1)}: {m.group(2)}')
    m = re.search(r'%MO(IN|MM)\*%', text)
    units = {'IN': 'inch', 'MM': 'mm'}.get(m.group(1) if m else '', '')
    m = re.search(r'%FS([^*]*)\*%', text)
    fmt = m.group(1) if m else ''
    draws = len(re.findall(r'D0?1\*', text))
    flashes = len(re.findall(r'D0?3\*', text))
    meta = [('Layer (from .SLK extension)', 'silkscreen legend'), ('Units', units or 'not stated'),
            ('Coordinate format', fmt or 'not stated'), ('Apertures defined', len(aps)),
            ('Draw commands (D01)', f'{draws:,}'), ('Flash commands (D03)', f'{flashes:,}')]
    pars = comments[:500] or ['(no G04 comments in this file)']
    summ = (f'Gerber photoplot (RS-274{"X" if "%FS" in text else "-D"}) for a PCB silkscreen layer: '
            f'{len(aps)} apertures, {draws:,} draws and {flashes:,} flashes'
            + (f'; header comments: {"; ".join(comments[:3])[:300]}' if comments else '') + '.')
    return {'kind': 'data', 'type': 'Gerber PCB silkscreen layer (not a SYLK spreadsheet)', 'summary': summ,
            'meta': meta, 'paragraphs': pars, 'outline': ([{'heading': 'Apertures'}] + aps[:300]) if aps else [],
            'notes': ['Coordinate data is not reproduced; only comments and aperture definitions are listed.']}


def _graphviz(path):
    text, _ = core.read_text(path, 5_000_000)
    m = re.search(r'\b(di)?graph\s+("?[\w ]*"?)\s*\{', text)
    gname = m.group(2).strip('" ') if m else ''
    labels = {}
    for nm in re.finditer(r'^\s*(\w+)\s*\[([^\]]*)\]', text, re.M):
        lm = re.search(r'label="((?:[^"\\]|\\.)*)"', nm.group(2))
        if lm and nm.group(1) not in ('node', 'edge', 'graph'):
            labels[nm.group(1)] = lm.group(1).replace('\\n', ' ').replace('\\l', ' ').strip()
    edges = re.findall(r'^\s*(\w+)\s*-[->]\s*(\w+)', text, re.M)
    outline = [{'heading': 'Nodes'}] + [f'{k}: {v}' for k, v in labels.items()]
    if edges:
        outline += [{'heading': 'Edges'}] + [f'{labels.get(a, a)} → {labels.get(b, b)}' for a, b in edges[:1000]]
    doxy = 'FreeSans' in text or 'Doxygen' in text
    summ = (f'Graphviz DOT graph{" " + repr(gname) if gname else ""}'
            f'{" generated by Doxygen" if doxy else ""} with {len(labels)} labelled nodes and {len(edges)} edges'
            + (': ' + ', '.join(list(labels.values())[:12]) if labels else '') + '.')
    return {'kind': 'source', 'type': 'Graphviz DOT graph (not a Word template)', 'summary': summ,
            'outline': outline, 'keywords': list(labels.values())[:8],
            'paragraphs': core.split_paragraphs(text), 'meta': [('Nodes', len(labels)), ('Edges', len(edges))]}

# ------------------------------------------------------------------ Office Open XML / ODF

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
P = '{http://schemas.openxmlformats.org/presentationml/2006/main}'
R_NS = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def _zip(path, ext):
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        meta, title = _ooxml_props(z, names)
        if 'word/document.xml' in names:
            r = _docx(z, names, ext)
        elif 'xl/workbook.xml' in names:
            r = _xlsx(path, z)
            if ext == 'xls':
                r.setdefault('notes', []).append('File has a .xls extension but is an Office Open XML (xlsx) workbook.')
        elif 'ppt/presentation.xml' in names:
            r = _pptx(z, names)
        elif 'content.xml' in names:
            r = _odf(z)
            m2, t2 = _odf_meta(z, names)
            meta += m2; title = title or t2
        else:
            r = {'kind': 'binary', 'type': f'ZIP container (.{ext})', 'outline': sorted(names)[:300],
                 'notes': ['ZIP file that is not a recognised Office document; entry list shown.']}
    if title and not r.get('title'):
        r['title'] = title
    if r.get('title'):
        meta = [m for m in meta if m[0] != 'Title']
    r['meta'] = meta + (r.get('meta') or [])
    return r


def _xml(z, name):
    with z.open(name) as f:
        return ET.parse(f).getroot()


def _ooxml_props(z, names):
    meta, title = [], ''
    if 'docProps/core.xml' in names:
        try:
            root = _xml(z, 'docProps/core.xml')
            vals = {}
            for el in root:
                tag = el.tag.split('}')[-1]
                if el.text and el.text.strip():
                    vals[tag] = el.text.strip()
            title = vals.get('title', '')
            for lab, k in (('Title', 'title'), ('Subject', 'subject'), ('Author', 'creator'),
                           ('Last modified by', 'lastModifiedBy'), ('Created', 'created'),
                           ('Modified', 'modified'), ('Revision', 'revision'), ('Keywords', 'keywords'),
                           ('Description', 'description'), ('Category', 'category')):
                if vals.get(k):
                    v = vals[k]
                    if k in ('created', 'modified'):
                        v = v.replace('T', ' ').rstrip('Z')
                    meta.append((lab, v))
        except Exception:
            pass
    if 'docProps/app.xml' in names:
        try:
            root = _xml(z, 'docProps/app.xml')
            vals = {el.tag.split('}')[-1]: (el.text or '').strip() for el in root}
            for lab, k in (('Application', 'Application'), ('Company', 'Company'), ('Pages', 'Pages'),
                           ('Words', 'Words'), ('Slides', 'Slides'), ('Template', 'Template')):
                if vals.get(k) and vals[k] != '0':
                    meta.append((lab, vals[k]))
        except Exception:
            pass
    return meta, title


def _wtext(el):
    """Text of a w:p (including runs inside hyperlinks, fields, text boxes)."""
    out = []
    for e in el.iter():
        t = e.tag
        if t == W + 't' or t == W + 'delText' and False:
            out.append(e.text or '')
        elif t == W + 'tab':
            out.append('\t')
        elif t in (W + 'br', W + 'cr'):
            out.append('\n')
        elif t == W + 'noBreakHyphen':
            out.append('-')
        elif t == W + 'sym':
            out.append('•')
    s = ''.join(out)
    s = re.sub(r'\t+', '  ', s)
    return _clean(s).strip()


def _docx(z, names, ext):
    styles = {}
    if 'word/styles.xml' in names:
        try:
            for s in _xml(z, 'word/styles.xml').iter(W + 'style'):
                sid = s.get(W + 'styleId')
                n = s.find(W + 'name')
                if sid:
                    styles[sid] = (n.get(W + 'val') if n is not None else sid) or sid
        except Exception:
            pass
    def is_heading(p):
        ppr = p.find(W + 'pPr')
        if ppr is None:
            return False
        st = ppr.find(W + 'pStyle')
        if ppr.find(W + 'outlineLvl') is not None:
            return True
        if st is None:
            return False
        nm = styles.get(st.get(W + 'val'), st.get(W + 'val') or '').lower()
        return nm.startswith('heading') or nm in ('title', 'subtitle') or nm.startswith('berschrift') or nm.startswith('überschrift')

    pars, ntables = [], 0
    def walk(parent):
        nonlocal ntables
        for ch in parent:
            tag = ch.tag
            if tag == W + 'p':
                t = _wtext(ch)
                if not t:
                    continue
                if is_heading(ch) and len(t) < 200 and '\n' not in t:
                    pars.append({'heading': t})
                else:
                    pars.append(t)
            elif tag == W + 'tbl':
                ntables += 1
                for tr in ch.iter(W + 'tr'):
                    cells = []
                    for tc in tr.findall(W + 'tc'):
                        cells.append(' / '.join(x for x in (_wtext(p) for p in tc.iter(W + 'p')) if x).replace('\n', ' / '))
                    row = _row(cells)
                    if row:
                        pars.append(row)
            elif tag in (W + 'sdt', W + 'sdtContent', W + 'customXml', W + 'body', W + 'ins', W + 'smartTag'):
                walk(ch)
    root = _xml(z, 'word/document.xml')
    body = root.find(W + 'body')
    walk(body if body is not None else root)
    # headers, footers, footnotes, endnotes, comments
    extra = []
    for nm in sorted(names):
        m = re.match(r'word/(header|footer|footnotes|endnotes|comments)\d*\.xml$', nm)
        if not m:
            continue
        try:
            ts = [_wtext(p) for p in _xml(z, nm).iter(W + 'p')]
            ts = [t for t in ts if t and not t.isdigit()]
            if ts:
                extra.append((m.group(1), ts))
        except Exception:
            pass
    seen = set()
    for kind, ts in extra:
        key = (kind, tuple(ts))
        if key in seen:
            continue
        seen.add(key)
        pars.append({'heading': kind.capitalize()})
        pars.extend(ts)
    imgs = sum(1 for n in names if n.startswith('word/media/'))
    r = {'kind': 'document', 'type': 'Microsoft Word document (Office Open XML' + (', macro-enabled)' if ext == 'docm' else ')'),
         'paragraphs': pars, 'meta': [('Tables', ntables), ('Embedded images', imgs)]}
    if not any(isinstance(p, str) for p in pars):
        r['notes'] = ['Document contains no text (images or drawings only).']
    return r


def _atext(el):
    paras = []
    for p in el.iter(A + 'p'):
        s = ''.join((e.text or '') if e.tag == A + 't' else ('\n' if e.tag == A + 'br' else '') for e in p.iter())
        s = _clean(s).strip()
        if s:
            paras.append(s)
    return paras


def _rels(z, name):
    d = os.path.dirname(name)
    rp = f'{d}/_rels/{os.path.basename(name)}.rels'
    out = {}
    try:
        for rel in _xml(z, rp):
            tgt = rel.get('Target', '')
            out[rel.get('Id')] = (rel.get('Type', ''), os.path.normpath(os.path.join(d, tgt)).replace('\\', '/') if not tgt.startswith('/') else tgt[1:])
    except Exception:
        pass
    return out


def _pptx(z, names):
    pres = _xml(z, 'ppt/presentation.xml')
    rels = _rels(z, 'ppt/presentation.xml')
    order = []
    lst = pres.find(P + 'sldIdLst')
    if lst is not None:
        for s in lst:
            rid = s.get(R_NS + 'id')
            if rid in rels:
                order.append(rels[rid][1])
    if not order:
        order = sorted((n for n in names if re.match(r'ppt/slides/slide\d+\.xml$', n)),
                       key=lambda n: int(re.findall(r'\d+', n)[-1]))
    pars = []
    for i, sl in enumerate(order, 1):
        try:
            root = _xml(z, sl)
        except Exception:
            continue
        title, body = '', []
        for sp in root.iter(P + 'sp'):
            ph = sp.find(f'.//{P}nvPr/{P}ph')
            txb = sp.find(P + 'txBody')
            if txb is None:
                continue
            ts = _atext(txb)
            if ph is not None and ph.get('type') in ('title', 'ctrTitle') and not title:
                title = re.sub(r'\s+', ' ', ' '.join(ts)).strip()
            else:
                body.extend(ts)
        for tbl in root.iter(A + 'tbl'):
            for tr in tbl.iter(A + 'tr'):
                row = _row([' / '.join(_atext(tc)) for tc in tr.findall(A + 'tc')])
                if row:
                    body.append(row)
        pars.append({'heading': f'Slide {i}' + (f': {title[:120]}' if title else '')})
        pars.extend(body)
        for typ, tgt in _rels(z, sl).values():
            if typ.endswith('/notesSlide') and tgt in names:
                try:
                    nroot = _xml(z, tgt)
                    notes = []
                    for sp in nroot.iter(P + 'sp'):
                        ph = sp.find(f'.//{P}nvPr/{P}ph')
                        if ph is not None and ph.get('type') == 'body':
                            notes += _atext(sp)
                    if notes:
                        pars.append('Speaker notes: ' + ' '.join(notes))
                except Exception:
                    pass
    return {'kind': 'document', 'type': 'Microsoft PowerPoint presentation (Office Open XML)', 'paragraphs': pars,
            'meta': [('Slides', len(order))] if 'docProps/app.xml' not in names else [],
            'summary': _deck_summary(pars)}


def _deck_summary(pars):
    titles, cur = [], None
    for p in pars + [{'heading': ''}]:
        if isinstance(p, dict):
            if cur is not None and cur:
                titles.append(re.sub(r'\s+', ' ', cur).strip())
            h = p['heading']
            cur = h.split(': ', 1)[1] if ': ' in h else ''
        elif cur == '':
            cur = p.split('\n')[0][:120]
    n = sum(1 for p in pars if isinstance(p, dict))
    if not titles:
        return ''
    first = titles[0]
    rest = [t for t in titles[1:] if t != first]
    seen, uniq = set(), []
    for t in rest:
        if t.lower() not in seen:
            seen.add(t.lower()); uniq.append(t)
    s = f'Presentation "{first}" ({n} slide{"s" if n != 1 else ""})'
    if uniq:
        s += '. Slide titles: ' + '; '.join(uniq[:25]) + (' …' if len(uniq) > 25 else '')
    return s[:1200] + '.'


ODF_T = '{urn:oasis:names:tc:opendocument:xmlns:text:1.0}'
ODF_TB = '{urn:oasis:names:tc:opendocument:xmlns:table:1.0}'
ODF_O = '{urn:oasis:names:tc:opendocument:xmlns:office:1.0}'


def _otext(el):
    out = []
    def rec(e):
        if e.text:
            out.append(e.text)
        for c in e:
            t = c.tag
            if t == ODF_T + 's':
                out.append(' ' * int(c.get(ODF_T + 'c', '1')))
            elif t == ODF_T + 'tab':
                out.append('  ')
            elif t == ODF_T + 'line-break':
                out.append('\n')
            elif t not in (ODF_T + 'note',):
                rec(c)
            if c.tail:
                out.append(c.tail)
    rec(el)
    return _clean(''.join(out)).strip()


def _odf(z):
    root = _xml(z, 'content.xml')
    body = root.find(f'{ODF_O}body')
    pars, alltexts, smeta, truncs, infos = [], [], [], [], []
    is_sheet = body is not None and body.find(ODF_O + 'spreadsheet') is not None
    def walk(parent):
        for ch in parent:
            t = ch.tag
            if t == ODF_T + 'h':
                s = _otext(ch)
                if s:
                    pars.append({'heading': s})
            elif t == ODF_T + 'p':
                s = _otext(ch)
                if s:
                    pars.append(s)
            elif t == ODF_TB + 'table':
                name = ch.get(ODF_TB + 'name', 'Table')
                rows = []
                for tr in ch.iter(ODF_TB + 'table-row'):
                    rep = min(int(tr.get(ODF_TB + 'number-rows-repeated', '1')), 1)
                    cells = []
                    for tc in tr:
                        if tc.tag not in (ODF_TB + 'table-cell', ODF_TB + 'covered-table-cell'):
                            continue
                        crep = min(int(tc.get(ODF_TB + 'number-columns-repeated', '1')), 50)
                        v = ' / '.join(x for x in (_otext(p) for p in tc.iter(ODF_T + 'p')) if x)
                        cells.extend([v] * crep)
                    rows.extend([cells] * rep)
                if is_sheet:
                    p, tx, tr_, inf = _sheet_block(name, rows, len(rows))
                    pars.extend(p); alltexts.extend(tx); smeta.append(name); infos.append(inf)
                    if tr_:
                        truncs.append(name)
                else:
                    for cells in rows:
                        r = _row(cells)
                        if r:
                            pars.append(r)
            else:
                walk(ch)
    walk(body if body is not None else root)
    if is_sheet:
        return _finish_sheets({'kind': 'data', 'type': 'OpenDocument spreadsheet', 'paragraphs': pars},
                              alltexts, smeta, truncs, infos, 'OpenDocument spreadsheet')
    return {'kind': 'document', 'type': 'OpenDocument text document', 'paragraphs': pars}


def _odf_meta(z, names):
    meta, title = [], ''
    if 'meta.xml' not in names:
        return meta, title
    try:
        for el in _xml(z, 'meta.xml').iter():
            tag = el.tag.split('}')[-1]
            v = (el.text or '').strip()
            if not v:
                continue
            lab = {'title': 'Title', 'initial-creator': 'Author', 'creator': 'Last modified by',
                   'creation-date': 'Created', 'date': 'Modified', 'generator': 'Application',
                   'editing-cycles': 'Revision'}.get(tag)
            if lab:
                meta.append((lab, v.replace('T', ' ')))
                if tag == 'title':
                    title = v
    except Exception:
        pass
    return meta, title

# ------------------------------------------------------------------ RTF

_RTF_SKIP = {'fonttbl', 'colortbl', 'stylesheet', 'listtable', 'listoverridetable', 'revtbl', 'rsidtbl',
             'generator', 'pict', 'object', 'objdata', 'themedata', 'colorschememapping', 'datastore',
             'latentstyles', 'xmlnstbl', 'fldinst', 'header', 'headerl', 'headerr', 'headerf', 'footer',
             'footerl', 'footerr', 'footerf', 'pntext', 'pntxta', 'pntxtb', 'filetbl', 'bkmkstart',
             'bkmkend', 'mmathPr', 'wgrffmtfilter', 'pgdsctbl', 'protusertbl', 'xe', 'tc', 'private',
             'blipuid', 'shppict', 'nonshppict', 'sp', 'docvar', 'userprops', 'passwordhash', 'ftnsep',
             'ftnsepc', 'aftnsep', 'aftnsepc', 'template', 'fchars', 'lchars', 'listtext', 'factoidname'}
_RTF_INFO = {'title': 'Title', 'subject': 'Subject', 'author': 'Author', 'operator': 'Last saved by',
             'company': 'Company', 'keywords': 'Keywords', 'doccomm': 'Comments'}
_RTF_TOK = re.compile(r"\\([a-zA-Z]{1,32})(-?\d{1,10})? ?|\\'([0-9a-fA-F]{2})|\\([^a-zA-Z])|([{}])|[\r\n]+|([^\\{}\r\n]+)")


def _rtf(path):
    with open(path, 'rb') as f:
        data = f.read(30_000_000).decode('latin-1')
    m = re.search(r'\\ansicpg(\d+)', data[:2000])
    cp = f'cp{m.group(1)}' if m else 'cp1252'
    try:
        ''.encode(cp)
    except LookupError:
        cp = 'cp1252'
    stack = []
    ignorable = False
    ucskip, curskip = 1, 0
    dest = None      # info field being captured
    out, hexbuf = [], []
    info = {}
    info_buf = []
    created = {}
    in_time = None

    def flush_hex():
        if hexbuf:
            s = bytes(hexbuf).decode(cp, 'replace')
            hexbuf.clear()
            emit(s)

    def emit(s):
        if dest:
            info_buf.append(s)
        elif not ignorable:
            out.append(s)

    for mt in _RTF_TOK.finditer(data):
        word, arg, hx, ch, brace, text = mt.groups()
        if hx is not None:
            if curskip > 0:
                curskip -= 1
                continue
            hexbuf.append(int(hx, 16))
            continue
        flush_hex()
        if brace == '{':
            curskip = 0
            stack.append((ucskip, ignorable, dest, in_time))
        elif brace == '}':
            curskip = 0
            if dest and stack and stack[-1][2] != dest:
                info[dest] = ''.join(info_buf).strip()
                info_buf.clear()
            if stack:
                ucskip, ignorable, dest, in_time = stack.pop()
        elif ch is not None:
            curskip = 0
            if ch == '~':
                emit('\xa0')
            elif ch in '{}\\':
                emit(ch)
            elif ch == '*':
                ignorable = True
            elif ch in '-':
                pass
            elif ch == '_':
                emit('-')
            elif ch in '\r\n':
                emit('\n')
        elif word is not None:
            curskip = 0
            if word in _RTF_SKIP:
                ignorable = True
            elif word in _RTF_INFO:
                dest = word; info_buf.clear()
            elif word in ('creatim', 'revtim'):
                in_time = word; created[word] = {}
            elif in_time and word in ('yr', 'mo', 'dy', 'hr', 'min'):
                created[in_time][word] = int(arg or 0)
            elif word == 'uc':
                ucskip = int(arg or 1)
            elif word == 'u':
                c = int(arg or 0)
                if c < 0:
                    c += 65536
                emit(chr(c)); curskip = ucskip
            elif word in ('par', 'sect', 'page'):
                emit('\n\n')
            elif word == 'line':
                emit('\n')
            elif word == 'tab':
                emit('\t')
            elif word == 'cell':
                emit('\x01')
            elif word == 'row':
                emit('\n\n')
            elif word in ('emdash',):
                emit('—')
            elif word in ('endash',):
                emit('–')
            elif word in ('bullet',):
                emit('•')
            elif word in ('lquote', 'rquote'):
                emit("'")
            elif word in ('ldblquote', 'rdblquote'):
                emit('"')
            elif word == 'bin':
                pass
        elif text is not None:
            if curskip > 0:
                n = min(curskip, len(text)); text = text[n:]; curskip -= n
            if text:
                emit(text)
    flush_hex()
    body = ''.join(out)
    pars = []
    for block in re.split(r'\n\s*\n', body):
        b = block.strip()
        if not b:
            continue
        if '\x01' in b:
            cells = [c.strip().replace('\n', ' ') for c in b.split('\x01')]
            b = _row(cells)
            if not b:
                continue
        else:
            b = re.sub(r'\t+', '  ', b)
            b = re.sub(r'[ \xa0]{3,}', '  ', b)
        b = _clean(b).strip()
        if b and not re.fullmatch(r'[_\-=\s]+', b):
            pars.append(b)
    meta = [(lab, info[k]) for k, lab in _RTF_INFO.items() if info.get(k)]
    for k, lab in (('creatim', 'Created'), ('revtim', 'Revised')):
        d = created.get(k)
        if d and d.get('yr'):
            meta.append((lab, f"{d['yr']:04d}-{d.get('mo', 1):02d}-{d.get('dy', 1):02d}"))
    gen = re.search(r'\{\\\*\\generator ([^;}]*)', data[:5000])
    if gen:
        meta.append(('Generator', gen.group(1).strip()))
    return {'kind': 'document', 'type': 'Rich Text Format document', 'title': info.get('title', ''),
            'paragraphs': pars, 'meta': meta}

# ------------------------------------------------------------------ WordPerfect

# WP 6+ "default extended international characters" 0x01..0x1F (WP charset 1, best effort)
_WP6_LOW = dict(zip(range(1, 32), 'ÇüéâäàåçêëèïîìÄÅÉæÆôöòûùÿÖÜø£Ø×ƒ'))
# WP charset 4 (typographic symbols), order as in libwpd
_WP_CS4 = dict(enumerate('●○■•*¶§¡¿«»£¥₧ƒªº½¼¢²ⁿ®©¤¾³‛’‘‟”“–—‹›○□†‡™℠℞'))
_WP_CS6 = {0x13: '±', 0x14: '≤', 0x15: '≥', 0x17: '÷'}


def _wp_ext(ch, cs):
    if cs == 0:
        return chr(ch) if 32 <= ch < 127 else ''
    if cs == 1:   # multinational: ASCII-like for common letters with diacritics -> best effort
        tbl = 'ˋ´ˆ¨~ˇ˘¯¸˛˙˝ʼ̀ÁáÂâÄäÀàÅåÆæÇçÉéÊêËëÈèÍíÎîÏïÌìÑñÓóÔôÖöÒòÚúÛûÜüÙùŸÿÃãĐđØøÕõÝýÐðÞþ'
        return tbl[ch - 23] if 23 <= ch < 23 + len(tbl) else ''
    if cs == 4:
        return _WP_CS4.get(ch, '')
    if cs == 6:
        return _WP_CS6.get(ch, '')
    if cs == 8:   # Greek
        g = 'ΑαΒβΒϐΓγΔδΕεΖζΗηΘθΙιΚκΛλΜμΝνΞξΟοΠπΡρΣσΣςΤτΥυΦφΧχΨψΩω'
        return g[ch] if ch < len(g) else ''
    return ''


def _wp_decode(data, start, ver6):
    """Decode WordPerfect 5.x / 6+ document area into text with \n for hard returns."""
    out = []
    i, n = start, len(data)
    hidden = False      # inside WP6 'invalid' (deleted, undo) text
    while i < n:
        b = data[i]
        if 0x20 <= b < 0x7f:
            j = i
            while j < n and 0x20 <= data[j] < 0x7f:
                j += 1
            if not hidden:
                out.append(data[i:j].decode('ascii'))
            i = j
            continue
        if hidden and ver6 and b != 0xf1 and b < 0xd0:
            i += 1
            continue
        if ver6:
            if b < 0x20:
                i += 1   # default extended chars: mapping uncertain, dropped
            elif b < 0xd0:   # single-byte functions
                if b in (0x80, 0x81, 0x87, 0x88):
                    out.append(' ')
                elif b in (0x84, 0x85, 0x86, 0x83):
                    out.append('-')
                elif b == 0xcf:          # soft end-of-line (word wrap)
                    if not (out and out[-1].endswith('-')):
                        out.append(' ')
                elif b in (0xcc, 0xcd, 0xce, 0xc7, 0xc8, 0xc9, 0xca, 0xcb):   # hard returns / page breaks
                    out.append('\n')
                i += 1
            elif b < 0xf0:   # variable-length: code sub len16 ... len16 code
                if i + 4 > n:
                    break
                sub = data[i + 1]
                size = data[i + 2] | (data[i + 3] << 8)
                if size < 4 or i + size > n or data[i + size - 1] != b:
                    i += 1; continue
                if b == 0xd0:      # end-of-line group
                    if sub in (0, 1, 2, 3, 0x14, 0x15, 0x16, 0x17):      # soft returns
                        if not (out and out[-1].endswith('-')):
                            out.append(' ')
                    elif sub == 0x0a:                                 # table cell
                        out.append('\x01')
                    elif 0x0b <= sub <= 0x12:                          # table row / table off
                        out.append('\n')
                    else:
                        out.append('\n')
                elif b == 0xe0:    # tab group
                    out.append('\t')
                i += size
            else:            # fixed-length 0xF0..0xFF: code ... code
                if b == 0xf0 and i + 3 < n and data[i + 3] == 0xf0:
                    if not hidden:
                        out.append(_wp_ext(data[i + 1], data[i + 2]))
                    i += 4; continue
                if b == 0xf1 and i + 4 < n and data[i + 4] == 0xf1:   # undo: 0 = invalid begin, 1 = end
                    if data[i + 1] == 0:
                        hidden = True
                    elif data[i + 1] == 1:
                        hidden = False
                    i += 5; continue
                j = data.find(bytes([b]), i + 1, i + 12)
                i = j + 1 if j > 0 else i + 1
        else:
            # WordPerfect 5.x
            if b in (0x0a, 0x0c):
                out.append('\n'); i += 1
            elif b == 0x0d:
                out.append(' '); i += 1
            elif b == 0x09:
                out.append('\t'); i += 1
            elif b < 0x20 or b == 0x7f:
                i += 1
            elif b < 0xc0:
                if b in (0x80, 0xa0):
                    out.append(' ')
                elif b in (0xa9, 0xaa, 0xab, 0xac):
                    out.append('-')
                i += 1
            elif b < 0xd0:
                sizes = {0xc0: 4, 0xc1: 9, 0xc2: 11, 0xc3: 3, 0xc4: 3, 0xc5: 5, 0xc6: 6, 0xc7: 7}
                if b == 0xc0 and i + 3 < n:
                    out.append(_wp_ext(data[i + 1], data[i + 2]))
                if b in sizes:
                    i += sizes[b]
                else:
                    j = data.find(bytes([b]), i + 1, i + 16)
                    i = j + 1 if j > 0 else i + 1
            else:
                if i + 4 > n:
                    break
                size = data[i + 2] | (data[i + 3] << 8)
                if b == 0xd4 and False:
                    pass
                if i + 4 + size <= n and data[i + 4 + size - 1] == b:
                    if b == 0xd0 and data[i + 1] in (0x01, 0x02):
                        pass
                    i += 4 + size
                else:
                    i += 1
    return ''.join(out)


def _wpd(path):
    with open(path, 'rb') as f:
        data = f.read(40_000_000)
    ptr = struct.unpack('<I', data[4:8])[0]
    ftype, major, minor = data[9], data[10], data[11]
    encrypted = struct.unpack('<H', data[12:14])[0] != 0
    ver6 = major >= 2
    verlab = {0: '5.x', 1: '5.x', 2: '6.0 or later'}.get(major, f'major {major}')
    typ = 'WordPerfect document' if ftype == 0x0a else f'WordPerfect file (type 0x{ftype:02x})'
    meta = [('WordPerfect format', f'{verlab} (file version {major}.{minor})')]
    if encrypted:
        return {'kind': 'binary', 'type': typ, 'meta': meta,
                'notes': ['Document is password-encrypted: text cannot be extracted.']}
    if ptr <= 0 or ptr >= len(data):
        ptr = 16
    text = _wp_decode(data, ptr, ver6)
    pars = []
    for ln in text.split('\n'):
        s = re.sub(r'[ \xa0]{2,}', ' ', ln.replace('\t', '  ').replace('\x01', ' ')).strip()
        if not s or re.fullmatch(r'[_\-=\.\s]+', s):
            continue
        fields = [f.strip() for f in re.split(r'[\t\x01]+', ln) if f.strip()]
        if '\x01' in ln and len(fields) >= 2 or len(fields) >= 3:
            s = ' | '.join(re.sub(r'\s{2,}', ' ', f) for f in fields)
        pars.append(s)
    # embedded-object and summary-packet strings from the prefix area (title etc.)
    title = ''
    m = re.search(rb'\x00{0,1}((?:[\x20-\x7e]\x00){4,80})\x00\x00', data[16:ptr]) if ver6 and ptr > 16 else None
    r = {'kind': 'document', 'type': f'{typ} (WordPerfect {verlab})', 'paragraphs': pars, 'meta': meta,
         'notes': ['WordPerfect has no converter installed: text decoded directly from the binary '
                   'format (formatting codes, embedded graphics and some special characters dropped; best effort).']}
    embeds = len(re.findall(rb'Corel Presentations|WPWin 6.0/OLE', data))
    if embeds:
        meta.append(('Embedded OLE/graphic objects', embeds))
    if not pars:
        rec = [x for x in _strings_from(data.replace(b'\x80', b' '), 8)
               if not re.search(r'WPWin|Presentations\.|METAFILEPICT|Embed Source|Object\(s\)|Corel', x)]
        if rec:
            r['paragraphs'] = rec[:3000]
            r['notes'].append('Document body area is empty or damaged: readable text strings recovered from the whole file instead.')
        else:
            r['notes'].append('No body text decoded (document area empty or damaged).')
    return r

# ------------------------------------------------------------------ Access / Jet

class _Jet:
    def __init__(self, data):
        self.d = data
        self.v4 = data[0x14] >= 1
        self.ps = 4096 if self.v4 else 2048
        self.np = len(data) // self.ps
        self._dp = None

    def page(self, n):
        return self.d[n * self.ps:(n + 1) * self.ps]

    def tdef(self, pg):
        p = self.page(pg)
        if not p or p[0] != 2:
            return None
        buf = bytearray(p)
        nxt = struct.unpack_from('<I', p, 4)[0]
        guard = 0
        while nxt and nxt < self.np and guard < 50:
            q = self.page(nxt)
            buf += q[8:]
            nxt = struct.unpack_from('<I', q, 4)[0]
            guard += 1
        b = bytes(buf)
        if self.v4:
            nrows = struct.unpack_from('<I', b, 16)[0]
            ncols = struct.unpack_from('<H', b, 45)[0]
            nridx = struct.unpack_from('<I', b, 51)[0]
            off = 63 + nridx * 12
            ce = 25
        else:
            nrows = struct.unpack_from('<I', b, 12)[0]
            ncols = struct.unpack_from('<H', b, 25)[0]
            nridx = struct.unpack_from('<I', b, 31)[0]
            off = 43 + nridx * 8
            ce = 18
        cols = []
        for i in range(ncols):
            e = off + i * ce
            if self.v4:
                ctype, cnum, ovar, flags, ofix, clen = b[e], struct.unpack_from('<H', b, e + 5)[0], \
                    struct.unpack_from('<H', b, e + 7)[0], b[e + 15], struct.unpack_from('<H', b, e + 21)[0], \
                    struct.unpack_from('<H', b, e + 23)[0]
            else:
                ctype, cnum, ovar, flags, ofix, clen = b[e], struct.unpack_from('<H', b, e + 1)[0], \
                    struct.unpack_from('<H', b, e + 3)[0], b[e + 13], struct.unpack_from('<H', b, e + 14)[0], \
                    struct.unpack_from('<H', b, e + 16)[0]
            cols.append({'type': ctype, 'num': cnum, 'var': ovar, 'fixed': bool(flags & 1), 'ofs': ofix, 'len': clen})
        p2 = off + ncols * ce
        for c in cols:
            if self.v4:
                ln = struct.unpack_from('<H', b, p2)[0]
                c['name'] = b[p2 + 2:p2 + 2 + ln].decode('utf-16-le', 'replace'); p2 += 2 + ln
            else:
                ln = b[p2]
                c['name'] = b[p2 + 1:p2 + 1 + ln].decode('cp1252', 'replace'); p2 += 1 + ln
        cols.sort(key=lambda c: c['num'])
        return {'rows': nrows, 'cols': cols}

    def data_pages(self, tdef_pg):
        if self._dp is None:
            self._dp = collections.defaultdict(list)
            for n in range(1, self.np):
                o = n * self.ps
                if self.d[o] == 1:
                    self._dp[struct.unpack_from('<I', self.d, o + 4)[0]].append(n)
        return self._dp.get(tdef_pg, [])

    def _rowbounds(self, pg, r):
        p = self.page(pg)
        cnt_off = 12 if self.v4 else 8
        nrows = struct.unpack_from('<H', p, cnt_off)[0]
        if r >= nrows:
            return None
        start = struct.unpack_from('<H', p, cnt_off + 2 + 2 * r)[0]
        end = self.ps if r == 0 else (struct.unpack_from('<H', p, cnt_off + 2 * r)[0] & 0x1fff)
        return p, start, end

    def rows(self, tdef_pg, td, limit):
        cols = td['cols']
        for pg in self.data_pages(tdef_pg):
            p = self.page(pg)
            cnt_off = 12 if self.v4 else 8
            nrows = struct.unpack_from('<H', p, cnt_off)[0]
            prev_end = self.ps
            for r in range(nrows):
                raw = struct.unpack_from('<H', p, cnt_off + 2 + 2 * r)[0]
                start = raw & 0x1fff
                end = prev_end
                prev_end = start
                if raw & 0x4000 or start >= end:
                    continue
                buf, s, e = p, start, end
                if raw & 0x8000:   # overflow pointer
                    tr, tp = p[start], struct.unpack_from('<I', p[start:start + 4].ljust(4, b'\0'))[0] >> 8
                    if tp >= self.np:
                        continue
                    rb = self._rowbounds(tp, tr)
                    if not rb:
                        continue
                    buf, s, e = rb
                    s &= 0x1fff
                try:
                    yield self.crack(buf, s, e - 1, cols)
                except Exception:
                    continue
                limit -= 1
                if limit <= 0:
                    return

    def crack(self, b, rs, re_, cols):
        if self.v4:
            ncols = struct.unpack_from('<H', b, rs)[0]; hdr = 2
        else:
            ncols = b[rs]; hdr = 1
        bms = (ncols + 7) // 8
        mask = b[re_ - bms + 1:re_ + 1]
        def present(cn):
            return cn < ncols and (mask[cn // 8] >> (cn % 8)) & 1
        nvar = sum(1 for c in cols if not c['fixed'])
        offs = []
        if nvar:
            if self.v4:
                rvc = struct.unpack_from('<H', b, re_ - bms - 1)[0]
                for i in range(rvc + 1):
                    offs.append(struct.unpack_from('<H', b, re_ - bms - 3 - i * 2)[0])
            else:
                rvc = b[re_ - bms]
                row_len = re_ - rs + 1
                nj = (row_len - 1) // 256
                col_ptr = re_ - bms - nj - 1
                if nj and (col_ptr - rs - rvc) // 256 < nj:
                    nj -= 1
                used = 0
                for i in range(rvc + 1):
                    while used < nj and i == b[re_ - bms - used - 1]:
                        used += 1
                    offs.append(b[col_ptr - i] + used * 256)
        vals = []
        for c in cols:
            t = c['type']
            if t == 1:
                vals.append('Yes' if present(c['num']) else 'No'); continue
            if not present(c['num']):
                vals.append(''); continue
            if c['fixed']:
                o = rs + hdr + c['ofs']
                raw = b[o:o + max(c['len'], {2: 1, 3: 2, 4: 4, 5: 8, 6: 4, 7: 8, 8: 8, 15: 16}.get(t, 0))]
            else:
                if c['var'] + 1 >= len(offs):
                    vals.append(''); continue
                raw = b[rs + offs[c['var']]:rs + offs[c['var'] + 1]]
            vals.append(self.value(t, raw))
        return vals

    def value(self, t, raw):
        try:
            if t == 2: return str(raw[0])
            if t == 3: return str(struct.unpack('<h', raw[:2])[0])
            if t == 4: return str(struct.unpack('<i', raw[:4])[0])
            if t == 5: return '%.4f' % (struct.unpack('<q', raw[:8])[0] / 10000)
            if t == 6: return _cell(float('%.7g' % struct.unpack('<f', raw[:4])[0]))
            if t == 7: return _cell(struct.unpack('<d', raw[:8])[0])
            if t == 8:
                d = struct.unpack('<d', raw[:8])[0]
                return _cell(datetime.datetime(1899, 12, 30) + datetime.timedelta(days=d))
            if t == 10: return self.text(raw)
            if t == 12: return self.memo(raw)
            if t == 11: return f'[OLE object, {len(raw)} bytes]'
            if t == 9: return raw.hex()
            if t == 15: return raw.hex()
        except Exception:
            pass
        return ''

    def text(self, raw):
        if not self.v4:
            return raw.decode('cp1252', 'replace')
        if raw[:2] == b'\xff\xfe':
            out, comp, i = [], True, 2
            while i < len(raw):
                if raw[i] == 0:
                    comp = not comp; i += 1; continue
                if comp:
                    out.append(chr(raw[i])); i += 1
                else:
                    out.append(raw[i:i + 2].decode('utf-16-le', 'replace')); i += 2
            return ''.join(out)
        return raw.decode('utf-16-le', 'replace')

    def memo(self, raw):
        if len(raw) < 12:
            return ''
        ln = struct.unpack_from('<I', raw, 0)[0]
        size = ln & 0x3fffffff
        if ln & 0x80000000:
            return self.text(raw[12:12 + size])
        if ln & 0x40000000:
            ptr = struct.unpack_from('<I', raw, 4)[0]
            rb = self._rowbounds(ptr >> 8, ptr & 0xff)
            if rb:
                p, s, e = rb
                return self.text(p[s & 0x1fff:e][:size])
        return f'[memo, {size} chars]'


def _mdb(path):
    with open(path, 'rb') as f:
        data = f.read(200_000_000)
    jet = _Jet(data)
    verlab = 'Jet 4 (Access 2000-2003)' if jet.v4 else 'Jet 3 (Access 97)'
    if data[0x14] >= 2:
        verlab = 'ACE (Access 2007+)'
    meta = [('Database engine', verlab), ('Pages', f'{jet.np:,} × {jet.ps} bytes')]
    sysobj = jet.tdef(2)
    if not sysobj:
        r = _strings(path, 'Microsoft Access database')
        r['meta'] = meta
        return r
    tables = []
    names = [c['name'] for c in sysobj['cols']]
    for row in jet.rows(2, sysobj, 100000):
        rec = dict(zip(names, row))
        try:
            typ = int(rec.get('Type') or 0) & 0x7fff
            flags = int(rec.get('Flags') or 0)
            oid = int(rec.get('Id') or 0)
        except ValueError:
            continue
        nm = rec.get('Name', '')
        if typ == 1 and not nm.startswith(('MSys', 'USys', '~')) and not (flags & 0x80000002):
            tables.append((nm, oid & 0x00ffffff))
        elif typ == 5 and not nm.startswith('~'):
            tables.append(('[query] ' + nm, None))
    pars, outline, alltexts, truncs, infos = [], [], [], [], []
    for nm, pg in tables:
        if pg is None:
            outline.append(nm); continue
        td = jet.tdef(pg)
        if not td:
            outline.append(f'{nm} (definition unreadable)'); continue
        cols = [c['name'] for c in td['cols']]
        outline.append(f"{nm}: {td['rows']:,} rows; columns: {', '.join(cols)}")
        def gen(pg=pg, td=td, cols=cols):
            yield cols
            yield from jet.rows(pg, td, MAX_ROWS + 1)
        p, t, tr, inf = _sheet_block(nm, gen(), td['rows'] + 1, label='Table')
        pars += p; alltexts += t[1:]
        inf['rows'] -= 1; inf['total'] = td['rows']
        infos.append(inf)
        if tr:
            truncs.append(nm)
    meta.append(('User tables', len([t for t in tables if t[1] is not None])))
    r = {'kind': 'data', 'type': 'Microsoft Access database', 'meta': meta,
         'outline': ([{'heading': 'Tables'}] + outline) if outline else [], 'paragraphs': pars}
    colset = ' '.join(o for o in outline).lower()
    if 'designator' in colset and ('mid x' in colset or 'center-x' in colset or 'ref x' in colset or ' x' in colset):
        r['type'] = 'Microsoft Access database: pick-and-place (component placement) table'
    kw = _partnos(alltexts)
    if kw:
        r['keywords'] = kw
    r['summary'] = _data_summary(f'Microsoft Access {verlab} database', infos, 'table')
    if 'Feeders' in [t[0] for t in tables] and 'PanelData' in [t[0] for t in tables]:
        r['type'] = 'Microsoft Access database: pick-and-place machine feeder setup'
        r['summary'] += ' Feeders lists the component reels/tubes/trays loaded on the pick-and-place machine (positions, package, speed, part in Comments).'
    if truncs:
        r['notes'] = [f'Large table(s) truncated to {MAX_ROWS:,} rows: ' + ', '.join(truncs)]
    if not tables:
        r.setdefault('notes', []).append('No user tables found in the database catalogue.')
    return r
