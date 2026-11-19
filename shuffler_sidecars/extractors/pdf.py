"""PDF extractor (PyMuPDF / fitz).

Per page: a {'heading': 'Page N'} followed by the page's text blocks in reading
order, one paragraph per block.  Hyphenated line breaks are joined, ordinary
wrapped lines become spaces, table-like blocks of short lines keep their line
breaks.  Running headers/footers repeated on most pages are dropped.
"""
import re, time, collections

EXTS = {'pdf'}

TIME_BUDGET = 85.0          # seconds of page extraction before we stop
MAX_CHARS = 3_200_000       # run.py caps rendered text at 3M anyway

_DIGITS = re.compile(r'\d+')
_WS = re.compile(r'[ \t ]+')
_PART = re.compile(r'(?<![A-Za-z0-9])([A-Z]{1,6}[\-]?\d{2,6}[A-Z0-9\-/]*|\d{1,4}[A-Z]{1,4}[\-]?\d{0,4}[A-Z0-9\-]*|[A-Z]{2,}[A-Za-z]*-\d+[A-Za-z0-9\-]*)(?![A-Za-z0-9])')
_NOT_PART = re.compile(r'^(?:\d+(?:ST|ND|RD|TH|MB|KB|GB|MHZ|KHZ|HZ|MM|CM|PM|AM|V|MA|K|M|S|X|DB|BIT|BITS)|REV\d*|PAGE\d*|DS\d?|UG\d?|FIG\d*|[A-Z]\d)$', re.I)

PAPER = {(612, 792): 'US Letter', (595, 842): 'A4', (612, 1008): 'US Legal',
         (792, 1224): 'Tabloid (11x17)', (842, 1191): 'A3', (1191, 1684): 'A2',
         (420, 595): 'A5', (1224, 1584): 'ANSI C', (1584, 2448): 'ANSI D'}


def _pdf_date(s):
    m = re.match(r"(?:D:)?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?", s or '')
    if not m:
        return s or ''
    y = int(m.group(1))
    if y < 1970 or y > 2100:
        return s
    out = f'{y}|{y - 1967}'
    if m.group(2):
        out += f' · {y}-{m.group(2)}' + (f'-{m.group(3)}' if m.group(3) else '')
        if m.group(4) and m.group(5):
            out += f' {m.group(4)}:{m.group(5)}'
    return out


def _page_size(rect):
    w, h = round(rect.width), round(rect.height)
    key = (min(w, h), max(w, h))
    name = ''
    for (a, b), n in PAPER.items():
        if abs(key[0] - a) <= 3 and abs(key[1] - b) <= 3:
            name = n
            break
    orient = 'landscape' if w > h else 'portrait'
    s = f'{w} x {h} pt ({rect.width / 72:.2f} x {rect.height / 72:.2f} in)'
    return f'{s}, {name + ", " if name else ""}{orient}'


def _clean_title(t):
    t = (t or '').strip().strip('\x00')
    t = re.sub(r'^(Microsoft (Word|PowerPoint|Excel) - |untitled$)', '', t, flags=re.I).strip()
    t = re.sub(r'\.(docx?|xlsx?|pptx?|rtf|wpd|vsd|sch|dsn|txt|pdf|jpe?g|png|bmp|tiff?|gif)$', '', t, flags=re.I).strip()
    if not t or t.lower().rstrip(':') in ('untitled', 'title', 'document', 'none', 'no title', 'notitle') or len(t) < 3:
        return ''
    if t.endswith(':'):
        return ''
    # authoring-tool file names (FrameMaker .book/.fm, Quark, InDesign, PageMaker ...) are not titles
    if ' ' not in t and re.search(r'\.(book|fm|qrk|qxd|qxp|indd|p65|pm\d|ps|eps|tmp|dvi|tex|at\d+|[a-z]{2,4}\d?)$', t, re.I):
        return ''
    if ' ' not in t and re.fullmatch(r'[a-z0-9_\-]+', t):
        return ''
    if sum(c.isalpha() for c in t) < 2:
        return ''
    return t


_BULLET_PUA = dict.fromkeys(map(ord, '\uf0b7\uf0a7\uf0a8\uf0d8\uf0fc\uf06e\uf075\uf0e0\uf02d\uf0d9\u25aa\u25cf\u25a0\u2219'), '•')
_LEADER = re.compile(r'\s*(?:\.\s?){4,}\s*|\s*(?:_\s?){6,}\s*')
_TOCLINE = re.compile(r'(?:…|\|) ?(?:[0-9]{1,4}|[ivxlc]{1,6}|[A-Z]?-?\d{1,3}-\d{1,3})$')
_LISTSTART = re.compile(r'^(?:[•\u2022\u25e6\-–\*]\s|\(?\d{1,2}[\.\)]\s|\(?[a-z][\.\)]\s|Step \d+)')


def _merge_rows(lines):
    """[(text, bbox, size, bold)] -> [(text, size, bold)]; lines sharing a baseline
    (table cells) are joined with ' | ' (or a space when the gap is small)."""
    out, prev = [], None
    for s, bb, size, bold in lines:
        if prev is not None:
            pb = prev
            same_row = abs((bb[1] + bb[3]) / 2 - (pb[1] + pb[3]) / 2) < max(2.0, 0.3 * (bb[3] - bb[1])) and bb[0] >= pb[2] - 1
            if same_row:
                gap = bb[0] - pb[2]
                t, sz, bd = out[-1]
                sep = ' ' if gap <= 8 else (' ' if re.fullmatch(r'[A-Z]?\d+(\.\d+)*\.?', t.strip()) and not out[-1][0].endswith('|') else ' | ')
                out[-1] = (t.rstrip() + sep + s.strip(), max(sz, size), bd and bold)
                prev = (pb[0], min(pb[1], bb[1]), bb[2], max(pb[3], bb[3]))
                continue
        out.append((s, size, bold))
        prev = bb
    return out


def _block_text(lines):
    """lines: [(text, size, bold)] (one per PDF text line) -> list of paragraph strings."""
    lines = [(_LEADER.sub(' … ', _WS.sub(' ', l.translate(_BULLET_PUA))).strip(), sz, bd) for l, sz, bd in lines]
    lines = [l for l in lines if l[0]]
    if not lines:
        return []
    # heading line(s) at the top of a block: larger or bold-only, followed by body text
    head = []
    if len(lines) >= 2:
        body = lines[1:]
        bsz = sorted(x[1] for x in body)[len(body) // 2]
        bbold = sum(x[2] for x in body) / len(body)
        t0, s0, b0 = lines[0]
        if len(t0) < 100 and t0[-1:] not in ',;' and ((s0 > bsz + 0.8) or (b0 and bbold < 0.5)) and \
                sum(len(x[0]) for x in body) > 40:
            head = [t0]
            lines = body
    lines = [l[0] for l in lines]
    nonsp = ''.join(lines).replace(' ', '')
    if nonsp and nonsp.count('\ufffd') / len(nonsp) > 0.4:
        return []
    if len(lines) == 1:
        return head + [lines[0]]
    avg = sum(len(l) for l in lines) / len(lines)
    longest = max(len(l) for l in lines)
    # table-ish / list-ish block: many short lines -> keep line breaks
    if len(lines) >= 3 and avg < 28 and longest < 45:
        return head + ['\n'.join(lines)]
    # table rows (cells already joined with ' | '): one row per line
    rows = sum(1 for l in lines if ' | ' in l)
    if rows >= 2 and rows >= 0.5 * len(lines):
        return head + ['\n'.join(lines)]
    pars, out = [], lines[0]
    for l in lines[1:]:
        if _TOCLINE.search(out):
            out += '\n' + l                      # table-of-contents entries: one per line
        elif _LISTSTART.match(l) and (out.rstrip()[-1:] in '.:;!?)' or _LISTSTART.match(out) or len(out) < 60):
            pars.append(out); out = l
        elif re.search(r'[A-Za-z]-$', out) and l[:1].islower():
            out = out[:-1] + l                     # de-hyphenate
        elif out.endswith(('-', '/')):
            out += l
        else:
            out += ' ' + l
    pars.append(out)
    res = head[:]
    for p in pars:                                  # inline bullets "a • b • c"
        res.extend(x.strip() for x in re.split(r'\s+(?=•\s)', p) if x.strip())
    return res


def _norm(t):
    return _DIGITS.sub('#', t.lower()).strip()


def _garbled(text):
    if not text:
        return False
    bad = sum(1 for c in text if c == '�' or (ord(c) < 32 and c not in '\n\t'))
    return bad / len(text) > 0.15


def _open_err(path, e):
    import os
    try:
        size = os.path.getsize(path)
    except Exception:
        size = -1
    if size == 0:
        return 'Empty file (0 bytes): nothing to extract.'
    if 0 < size < 1024:
        return f'PDF could not be opened: only {size} bytes, file is truncated (header only).'
    msg = str(e).split(' as type pdf')[0]
    msg = re.sub(r"Failed to open file '.*'", 'Failed to open file', msg)
    return f'PDF could not be opened ({type(e).__name__}: {msg[:120]}). File may be damaged or truncated.'


def extract(path):
    try:
        import fitz
    except Exception as e:
        return {'kind': 'document', 'type': 'PDF document',
                'notes': [f'PyMuPDF not available ({e}); text not extracted.']}
    notes, meta = [], []
    try:
        fitz.TOOLS.mupdf_display_errors(False)
        fitz.TOOLS.mupdf_display_warnings(False)
    except Exception:
        pass
    try:
        doc = fitz.open(path, filetype='pdf')
    except Exception as e:
        return {'kind': 'binary', 'type': 'PDF document (unreadable)',
                'notes': [_open_err(path, e)]}
    try:
        return _extract(fitz, doc, notes, meta)
    finally:
        try:
            doc.close()
        except Exception:
            pass


def _extract(fitz, doc, notes, meta):
    if doc.needs_pass:
        if not doc.authenticate(''):
            return {'kind': 'document', 'type': 'PDF document (encrypted)',
                    'meta': [('Encrypted', 'yes, password required')],
                    'notes': ['PDF is password-protected; text could not be extracted.']}
    if doc.is_encrypted or doc.metadata and doc.metadata.get('encryption'):
        enc = (doc.metadata or {}).get('encryption')
        if enc:
            meta.append(('Encryption', f'{enc} (opened without password)'))

    md = doc.metadata or {}
    n = doc.page_count
    meta.append(('Pages', n))
    title = _clean_title(md.get('title'))
    for label, k in (('PDF title', 'title'), ('PDF author', 'author'), ('PDF subject', 'subject'),
                     ('PDF keywords', 'keywords'), ('Creator application', 'creator'), ('PDF producer', 'producer')):
        v = (md.get(k) or '').strip().replace('\n', ' ')
        if v:
            meta.append((label, v[:300]))
    if md.get('creationDate'):
        meta.append(('PDF created (file date, not design date)', _pdf_date(md['creationDate'])))
    if md.get('modDate') and md.get('modDate') != md.get('creationDate'):
        meta.append(('PDF modified (file date)', _pdf_date(md['modDate'])))
    if md.get('format'):
        meta.append(('PDF version', md['format']))

    flags = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP
    t0 = time.time()
    pages = []                  # (pno, [(y0, y1, height, text)])
    no_text, blank, garbled, scanned, vector = [], [], [], [], []
    sizes = collections.Counter()
    first_page_big = ''
    stopped_at = None
    total = 0
    for pno in range(n):
        if time.time() - t0 > TIME_BUDGET or total > MAX_CHARS:
            stopped_at = pno
            break
        try:
            page = doc.load_page(pno)
        except Exception as e:
            pages.append((pno, None))
            notes.append(f'Page {pno + 1} could not be read ({type(e).__name__}).')
            continue
        rect = page.rect
        if pno < 50:
            sizes[_page_size(rect)] += 1
        try:
            d = page.get_text('dict', flags=flags)
        except Exception as e:
            pages.append((pno, None))
            notes.append(f'Page {pno + 1} text extraction failed ({type(e).__name__}).')
            continue
        blocks = []
        best = (0, '')
        for b in d.get('blocks', []):
            if b.get('type') != 0:
                continue
            lines = []
            for ln in b.get('lines', []):
                s = ''.join(sp.get('text', '') for sp in ln.get('spans', []))
                if s.strip():
                    sps = [sp for sp in ln.get('spans', []) if sp.get('text', '').strip()]
                    size = max((sp.get('size', 0) for sp in sps), default=0)
                    bold = bool(sps) and all((sp.get('flags', 0) & 16) or 'bold' in sp.get('font', '').lower() for sp in sps)
                    lines.append((s, ln.get('bbox') or (0, 0, 0, 0), size, bold))
                if pno == 0:
                    for sp in ln.get('spans', []):
                        if sp.get('size', 0) > best[0] and len(sp.get('text', '').strip()) > 3:
                            best = (sp['size'], s.strip())
            y0, y1 = b['bbox'][1], b['bbox'][3]
            lines = _merge_rows(lines)
            ptxt = _block_text(lines)
            if not ptxt and lines and any('\ufffd' in l[0] for l in lines):
                if not garbled or garbled[-1] != pno + 1:
                    garbled.append(pno + 1)
            for t in ptxt:
                blocks.append((y0, y1, rect.height or 1, t))
        if pno == 0:
            first_page_big = best[1]
        if not blocks:
            try:
                if page.get_images(full=False):
                    scanned.append(pno + 1); no_text.append(pno + 1)
                elif page.get_drawings()[:1]:
                    vector.append(pno + 1); no_text.append(pno + 1)
                else:
                    blank.append(pno + 1)
            except Exception:
                no_text.append(pno + 1); scanned.append(pno + 1)
        else:
            txt = ' '.join(b[3] for b in blocks)
            total += len(txt)
            if _garbled(txt) and (not garbled or garbled[-1] != pno + 1):
                garbled.append(pno + 1)
        pages.append((pno, blocks))

    # running headers / footers: same normalised text in top/bottom 8% on >= 50% of pages
    text_pages = [p for p in pages if p[1]]
    drop = set()
    if len(text_pages) >= 4:
        cnt = collections.Counter()
        for _, blocks in text_pages:
            seen = set()
            for y0, y1, h, t in blocks:
                if (y1 < 0.09 * h or y0 > 0.91 * h) and len(t) < 160:
                    seen.add(_norm(t))
            cnt.update(seen)
        thr = max(3, 0.35 * len(text_pages))
        drop = {k for k, v in cnt.items() if v >= thr and k not in ('#', '')} | \
               {k for k, v in cnt.items() if k in ('#', 'page #', '- # -', 'page # of #', '# of #') and v >= 3}
        if drop:
            notes.append(f'{len(drop)} running header/footer line(s) repeated on most pages were omitted from the full text.')

    def _compact(pars):
        # runs of >= 4 tiny single-line fragments (schematic labels, grid refs) -> one line
        out, run = [], []
        for t in pars + [None]:
            if t is not None and len(t) <= 20 and '\n' not in t:
                run.append(t); continue
            if len(run) >= 4:
                out.append(' · '.join(run))
            else:
                out.extend(run)
            run = []
            if t is not None:
                out.append(t)
        return out

    paragraphs = []
    for pno, blocks in pages:
        paragraphs.append({'heading': f'Page {pno + 1}'})
        if blocks is None:
            paragraphs.append('[page could not be read]')
            continue
        if not blocks:
            if (pno + 1) in scanned:
                paragraphs.append('[no text layer – scanned image]')
            elif (pno + 1) in vector:
                paragraphs.append('[no text layer – vector drawing]')
            else:
                paragraphs.append('[blank page]')
            continue
        kept = [t for y0, y1, h, t in blocks
                if not (drop and (y1 < 0.09 * h or y0 > 0.91 * h) and _norm(t) in drop)]
        paragraphs.extend(_compact(kept))
    if stopped_at is not None:
        notes.append(f'Text extraction stopped at page {stopped_at} of {n} (time/size budget); later pages not included.')

    has_text = len(text_pages) > 0
    if sizes:
        common = sizes.most_common()
        meta.append(('Page size', common[0][0] + (f' (+{len(common) - 1} other size(s))' if len(common) > 1 else '')))
    if not has_text:
        layer = 'none'
    elif no_text:
        layer = f'yes on {len(text_pages)} of {len(pages)} pages'
    else:
        layer = 'yes'
    meta.append(('Text layer', layer))
    toc = []
    try:
        toc = doc.get_toc(simple=True)
    except Exception:
        pass
    if toc:
        meta.append(('Bookmarks', len(toc)))

    def pages_str(lst):
        return ', '.join(map(str, lst[:30])) + (f' … (+{len(lst) - 30} more)' if len(lst) > 30 else '')

    r = {'kind': 'document', 'type': 'PDF document', 'meta': meta, 'notes': notes}
    if n == 0:
        r['type'] = 'PDF document (damaged)'
        notes.append('PDF has no readable pages: the page tree is missing or broken (file is probably truncated, '
                     'e.g. an incomplete download); no text could be extracted.')
    elif not has_text:
        if scanned:
            r['type'] = 'Scanned PDF (no text layer)'
            notes.append(f'No page has a text layer ({len(scanned)} scanned-image page(s)) – needs OCR to recover text.')
            if vector:
                notes.append(f'{len(vector)} further page(s) are vector drawings without a text layer.')
        elif vector:
            r['type'] = 'PDF vector drawing (no text layer)'
            notes.append(f'No page has a text layer: {len(vector)} vector-drawing page(s) (CAD/plot output with text drawn as outlines) – '
                         'only OCR of a rendering could recover labels.')
        else:
            notes.append('All pages are blank (no text, no images).')
        paragraphs = []
    else:
        if scanned:
            if len(scanned) <= 5:
                for p in scanned:
                    notes.append(f'Page {p} has no text layer (scanned image) – needs OCR.')
            else:
                notes.append(f'{len(scanned)} pages have no text layer (scanned images) – need OCR: pages {pages_str(scanned)}.')
        if vector:
            notes.append(f'{len(vector)} page(s) are vector drawings with no text layer: pages {pages_str(vector)}.')
        if blank:
            notes.append(f'{len(blank)} blank page(s): {pages_str(blank)}.')
        if garbled:
            notes.append(f'{len(garbled)} page(s) contain text in fonts without Unicode mapping (typically figure labels or equations; unreadable runs omitted): pages {pages_str(garbled)}.')
    r['paragraphs'] = paragraphs

    if not title and first_page_big and has_text:
        t = _clean_title(first_page_big)
        if t and len(t) <= 150 and (' ' in t or re.search(r'\d', t)):
            title = t
    if title:
        r['title'] = title

    # keywords: part numbers / model codes from title, filename-free metadata, and page 1 first
    seed = ' '.join([md.get('title') or '', md.get('subject') or '', md.get('keywords') or '', title or ''])
    first = ' '.join(b[3] for b in (pages[0][1] or [])) if pages and pages[0][1] else ''
    kw, seen = [], set()
    for src in (seed, first[:6000]):
        for m in _PART.finditer(src):
            w = m.group(1).strip('-/')
            if len(w) < 3 or len(w) > 24 or _NOT_PART.match(w) or w.lower() in seen:
                continue
            nl, nd = sum(c.isalpha() for c in w), sum(c.isdigit() for c in w)
            if len(w) < 4 or nd < 1 or (nd < 2 and len(w) < 5):
                continue
            if nl < 2 and not (nl == 1 and w[0].isdigit() and len(w) >= 5):
                continue
            if re.fullmatch(r'(19|20)\d\d', re.sub(r'\D', '', w)) and len(re.sub(r'\d', '', w)) <= 1:
                continue
            seen.add(w.lower()); kw.append(w)
            if len(kw) >= 8:
                break
        if len(kw) >= 8:
            break
    for k in (md.get('keywords') or '').replace(';', ',').split(','):
        k = k.strip()
        if 2 < len(k) < 40 and not re.search(r'[:$=]', k) and k.lower() not in seen and len(kw) < 10:
            seen.add(k.lower()); kw.append(k)
    if kw:
        r['keywords'] = kw

    if toc and all(re.fullmatch(r'(page|p\.?)\s*\d+|\d+', t.strip(), re.I) for _, t, _ in toc):
        toc = []
    if toc:
        outline = []
        for lvl, t, pg in toc[:2000]:
            outline.append(('  ' * 0) + ('· ' * (lvl - 1)) + f'{t.strip()} (p. {pg})')
        if len(toc) > 2000:
            outline.append(f'… {len(toc) - 2000} more bookmarks')
        r['outline'] = [{'heading': 'Bookmarks / table of contents'}] + outline

    subj = (md.get('subject') or '').strip()
    if len(subj) > 40 and sum(c.isalpha() for c in subj) > 20:
        r['summary'] = subj
    elif paragraphs:
        # summarise prose only: skip TOC lines, table rows and placeholders
        prose = [p for p in paragraphs if isinstance(p, str) and len(p) > 60 and p.count(' | ') < 2
                 and '…' not in p and not p.startswith('[') and p.count('\n') < 3
                 and not re.search(r'[A-Za-z]:\\|\\\\', p) and p.count(' · ') < 3]
        try:
            import core
            auto = core.summarize(prose) if prose else ''
        except Exception:
            auto = ''
        if auto:
            r['summary'] = (title + ' — ' + auto) if title and ' ' in title and title.lower() not in auto.lower() else auto
        elif title:
            r['summary'] = title
    return r
