"""Misc extractor: archives, Java bytecode, images, audio/video, build/shell
scripts and files without an extension.

Everything is read in place and in memory only: archives are listed from their
central directory / headers (never extracted to disk), media files only have
their headers parsed, and nothing is ever executed.
"""
import os, re, struct, datetime, collections

try:
    import core
except Exception:  # pragma: no cover
    core = None

EXTS = {'zip', 'jar', 'war', 'rar', '7z', 'gz', 'tgz', 'tar', 'class',
        'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tif', 'tiff', 'pcx', 'ico', 'wmf', 'emf', 'svg', 'wpg',
        'wav', 'm4a', 'mp3', 'avi', 'mp4', 'mov', 'wma',
        'sh', 'bash', 'bat', 'cmd', 'mak', 'mk', 'make', 'makefile', 'am', 'in', 'pl', 'awk', 'sed', ''}
NAMES = {'makefile', 'gnumakefile', 'readme', 'license', 'copying', 'changelog', 'todo', 'install',
         'news', 'configure'}

ARCHIVE_CAP = 300            # entries listed in the outline
TEXT_ENTRY_MAX = 256 * 1024  # largest archive member read in memory as text
TEXT_TOTAL_MAX = 1024 * 1024
TEXT_EXTS = {'txt', 'md', 'mf', 'ini', 'cfg', 'conf', 'prjpcb', 'prjfpg', 'prjscr', 'csv', 'properties',
             'readme', 'log', 'htm', 'html', 'xml', 'json', 'bat', 'sh', 'c', 'h', 'v', 'vhd', 'ucf',
             'qsf', 'tcl', 'java', 'asm', 's', 'mak', 'bom', 'rep', 'drr', 'outjob', 'lst', 'nfo', 'diz'}
TEXT_NAMES = {'readme', 'license', 'copying', 'changelog', 'manifest.mf', 'install', 'news', 'todo'}


# ======================================================================== helpers
def _wy(dt):
    """datetime/(y,m,d,...) -> 'YYYY|n · YYYY-MM-DD HH:MM'."""
    try:
        if isinstance(dt, (tuple, list)):
            dt = datetime.datetime(*dt[:6])
        return f'{dt.year}|{dt.year - 1967} · {dt:%Y-%m-%d %H:%M}'
    except Exception:
        return str(dt)


def _ts(t):
    try:
        if t <= 0:
            return ''
        return _wy(datetime.datetime.fromtimestamp(t))
    except Exception:
        return ''


def _size(n):
    n = float(n)
    for u in ('bytes', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or u == 'TB':
            return f'{int(n):,} bytes' if u == 'bytes' else f'{n:.1f} {u}'
        n /= 1024


def _pl(n, word, plural=None):
    return f'{n:,} {word if n == 1 else (plural or word + "s")}'


def _dur(sec):
    try:
        sec = float(sec)
    except Exception:
        return ''
    if sec <= 0:
        return ''
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return (f'{int(h)}:{int(m):02d}:{s:05.2f}' if h else f'{int(m)}:{s:05.2f}') + f' ({sec:.2f} s)'


def _decode(b):
    if b.startswith(b'\xef\xbb\xbf'):
        b = b[3:]
    if b[:2] in (b'\xff\xfe', b'\xfe\xff'):
        try:
            return b.decode('utf-16')
        except Exception:
            pass
    for enc in ('utf-8', 'cp1252', 'latin-1'):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode('latin-1', 'replace')


def _split(text):
    if core:
        return core.split_paragraphs(text)
    return [b.strip() for b in re.split(r'\n\s*\n', text.replace('\r', '')) if b.strip()]


def _read_text(path):
    if core:
        return core.read_text(path)
    with open(path, 'rb') as f:
        return _decode(f.read()), False


def _is_binary_bytes(chunk):
    if not chunk:
        return False
    if chunk[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return False
    if b'\x00' in chunk:
        return True
    ctrl = sum(1 for b in chunk if b < 9 or (13 < b < 32 and b != 26))
    return ctrl / len(chunk) > 0.10


def _strings(data, minlen=6, cap=1500):
    seen, out = set(), []
    for m in re.finditer(rb'[\x20-\x7e\t]{%d,}' % minlen, data):
        s = m.group(0).decode('ascii').strip()
        if len(s) < minlen or s in seen:
            continue
        if sum(c.isalpha() for c in s) < len(s) * 0.5:
            continue
        seen.add(s)
        out.append(s[:300])
        if len(out) >= cap:
            break
    return out


def _strings_pars(strs, per=25):
    return ['\n'.join(strs[i:i + per]) for i in range(0, len(strs), per)]


_DELEGATES = {}


def _delegate(path, ext, why=''):
    """Run another family's extractor for `ext` if one exists (lazy import)."""
    import importlib
    if ext not in _DELEGATES:
        _DELEGATES[ext] = None
        d = os.path.dirname(os.path.abspath(__file__))
        try:
            names = sorted(os.listdir(d))
        except Exception:
            names = []
        for fn in names:
            if not fn.endswith('.py') or fn.startswith('_') or fn == 'misc.py':
                continue
            try:
                m = importlib.import_module('extractors.' + fn[:-3])
            except Exception:
                continue
            if ext in {e.lower() for e in getattr(m, 'EXTS', ())}:
                _DELEGATES[ext] = m
                break
    m = _DELEGATES[ext]
    if m is None:
        return None
    try:
        r = m.extract(path)
    except Exception:
        return None
    if not r:
        return None
    r = dict(r)
    r['notes'] = list(r.get('notes') or []) + [
        f'No usable extension{why}: content sniffed as `.{ext}` and parsed by the '
        f'`{m.__name__.split(".")[-1]}` extractor.']
    return r


# ======================================================================== zip / jar
def _altium_history(name):
    m = re.match(r'^(.*)\.~\((\d+)\)\.([A-Za-z0-9]+)\.zip$', name, re.I)
    if m:
        return f'{m.group(1)}.{m.group(3)}', int(m.group(2))
    return None


def _zip(path, kind_ext='zip'):
    import zipfile
    name = os.path.basename(path)
    try:
        z = zipfile.ZipFile(path)
    except Exception as e:
        return _sniff_bad_archive(path, f'ZIP ({type(e).__name__}: {str(e)[:80]})')
    with z:
        infos = z.infolist()
        files = [i for i in infos if not i.is_dir()]
        total = sum(i.file_size for i in files)
        comp = sum(i.compress_size for i in files)
        dates = []
        for i in files:
            try:
                dates.append(datetime.datetime(*i.date_time))
            except Exception:
                pass
        newest = max(dates) if dates else None
        oldest = min(dates) if dates else None
        enc = any(i.flag_bits & 1 for i in files)
        meta = [('Entries', _pl(len(files), 'file') + (', ' + _pl(len(infos) - len(files), 'folder') if len(infos) > len(files) else '')),
                ('Uncompressed size', _size(total)),
                ('Compressed size', _size(comp) + (f' ({100 * comp / total:.0f}%)' if total else ''))]
        if newest:
            meta.append(('Newest entry', _wy(newest)))
        if oldest and oldest != newest:
            meta.append(('Oldest entry', _wy(oldest)))
        if enc:
            meta.append(('Encrypted', 'yes (some or all entries password-protected)'))
        if z.comment:
            meta.append(('Archive comment', _decode(z.comment)[:300]))
        exts = collections.Counter((os.path.splitext(i.filename)[1].lower() or '(none)') for i in files)
        if exts:
            meta.append(('Entry types', ', '.join(f'{e} ×{n}' for e, n in exts.most_common(12))))
        outline = [{'heading': f'Entries ({len(infos):,}): name · size in bytes · date'}]
        for i in infos[:ARCHIVE_CAP]:
            try:
                d = f'{datetime.datetime(*i.date_time):%Y-%m-%d %H:%M}'
            except Exception:
                d = '?'
            if i.is_dir():
                outline.append(f'`{i.filename}`')
            else:
                outline.append(f'`{i.filename}` · {i.file_size:,} · {d}')
        if len(infos) > ARCHIVE_CAP:
            outline.append(f'… and {len(infos) - ARCHIVE_CAP:,} more entries')
        # small text members, read in memory
        pars, used, notes = [], 0, []
        for i in files:
            base = os.path.basename(i.filename).lower()
            ext = base.rsplit('.', 1)[1] if '.' in base else ''
            if not (ext in TEXT_EXTS or base in TEXT_NAMES or base.startswith('readme')):
                continue
            if i.flag_bits & 1 or i.file_size > TEXT_ENTRY_MAX or used + i.file_size > TEXT_TOTAL_MAX:
                continue
            try:
                data = z.read(i)
            except Exception:
                continue
            if _is_binary_bytes(data[:4096]):
                continue
            used += len(data)
            pars.append({'heading': f'Entry: {i.filename}'})
            pars.extend(_split(_decode(data)))
        if used:
            notes.append('Text of small text entries read in memory (archive not extracted).')
        r = {'kind': 'data', 'meta': meta, 'outline': outline, 'paragraphs': pars, 'notes': notes,
             'type': 'ZIP archive'}
        hist = _altium_history(name)
        parent = os.path.basename(os.path.dirname(path)).lower()
        kw = []
        if hist:
            doc, n = hist
            r['type'] = 'Altium Designer history snapshot (ZIP)'
            r['title'] = f'{doc} — history revision {n}'
            when = f', saved {newest:%Y-%m-%d %H:%M}' if newest else ''
            r['summary'] = (f'Altium Designer local-history snapshot #{n} of {doc} '
                            f'({_pl(len(files), "entry", "entries")}, {_size(total)}{when}). '
                            f'Altium writes these automatic backup copies into the History folder each time the '
                            f'document is saved.')
            kw = [doc, os.path.splitext(doc)[0], 'Altium history']
        elif kind_ext in ('jar', 'war') or any(i.filename == 'META-INF/MANIFEST.MF' for i in infos[:50]):
            _jar_info(z, infos, r, kind_ext)
            kw = r.pop('_kw', [])
        else:
            top = collections.Counter(i.filename.split('/')[0] for i in infos)
            if len(top) == 1:
                lvl2 = collections.Counter('/'.join(i.filename.split('/')[:2]) for i in infos if i.filename.count('/') >= 1
                                           and i.filename.split('/')[1])
                if lvl2:
                    top = lvl2
            tops = ', '.join(t for t, _ in top.most_common(6))
            when = f', newest entry {newest:%Y-%m-%d}' if newest else ''
            if name.lower().startswith('takeout') or any('takeout/' in i.filename.lower() for i in infos[:20]):
                r['type'] = 'Google Takeout export (ZIP)'
            elif exts and set(exts) <= {'.gbr', '.gtl', '.gbl', '.gto', '.gbo', '.gts', '.gbs', '.gtp', '.gbp',
                                        '.gko', '.gm1', '.drl', '.txt', '.g1', '.g2', '.gd1', '.gg1', '.top',
                                        '.bot', '.ger', '.pho', '.art', '.drr', '.rep', '.apr', '.gpt', '.gpb',
                                        '.ldp', '.cam', '.xln', '.gnd', '.pwr', '(none)', '.zip', '.pdf', '.tsm', '.bsm', '.slk',
                                        '.ncd', '.ssk', '.bsk', '.tsp', '.bsp', '.smt', '.smb', '.spt', '.spb',
                                        '.sst', '.ssb', '.fab', '.dri', '.gpi', '.nc', '.cmp', '.sol', '.plc',
                                        '.stc', '.sts', '.gtd', '.gbd', '.gm2', '.gm3', '.gp1', '.gp2', '.ipc',
                                        '.out', '.lst', '.htm', '.csv', '.xls', '.bom', '.pnp', '.dxf'} \
                    and any(e.startswith('.g') or e in ('.drl', '.pho', '.art', '.top', '.bot', '.tsm', '.ncd', '.slk') for e in exts):
                r['type'] = 'PCB fabrication (Gerber/drill) package (ZIP)'
            r['summary'] = (f'{r["type"]} containing {_pl(len(files), "file")} '
                            f'({_size(total)} uncompressed{when}).'
                            + (f' Top-level items: {tops}.' if tops else ''))
            kw = [os.path.splitext(i.filename.split('/')[-1])[0] for i in files[:8]]
        r['keywords'] = kw
        return r


def _jar_info(z, infos, r, kind_ext):
    r['type'] = 'Java web archive (WAR)' if kind_ext == 'war' else 'Java archive (JAR)'
    man = {}
    try:
        txt = _decode(z.read('META-INF/MANIFEST.MF'))
        txt = re.sub(r'\r?\n ', '', txt)
        for ln in txt.splitlines():
            if ':' in ln:
                k, v = ln.split(':', 1)
                man.setdefault(k.strip(), v.strip())
    except Exception:
        pass
    classes = [i.filename for i in infos if i.filename.endswith('.class')]
    pkgs = collections.Counter('.'.join(c.split('/')[:-1]) or '(default package)' for c in classes)
    for k in ('Main-Class', 'Implementation-Title', 'Implementation-Version', 'Implementation-Vendor',
              'Specification-Title', 'Specification-Version', 'Bundle-Name', 'Bundle-Version',
              'Created-By', 'Built-By', 'Ant-Version', 'Class-Path'):
        if man.get(k):
            r['meta'].append((f'Manifest {k}', man[k][:300]))
    r['meta'].append(('Classes', f'{len(classes):,} in {_pl(len(pkgs), "package")}'))
    if pkgs:
        r['outline'] = [{'heading': f'Packages ({len(pkgs)})'}] + \
            [f'`{p}` — {n} class{"es" if n != 1 else ""}' for p, n in sorted(pkgs.items())[:200]] + r['outline']
    title = man.get('Implementation-Title') or man.get('Bundle-Name') or ''
    ver = man.get('Implementation-Version') or man.get('Bundle-Version') or ''
    javas = [i.filename for i in infos if i.filename.endswith('.java')]
    if not classes and javas:
        pkgs = collections.Counter('.'.join(c.split('/')[:-1]) or '(default package)' for c in javas)
        r['type'] = 'Java source archive (JAR of .java files)'
        s = f'{r["type"]}{" " + title if title else ""}{" version " + ver if ver else ""}: {_pl(len(javas), "source file")}'
    else:
        s = f'{r["type"]}{" " + title if title else ""}{" version " + ver if ver else ""}: {_pl(len(classes), "class", "classes")}'
    if pkgs:
        s += ' in packages ' + ', '.join(p for p, _ in pkgs.most_common(6))
    s += '.'
    if man.get('Main-Class'):
        s += f' Runnable; Main-Class {man["Main-Class"]}.'
    r['summary'] = s
    if title:
        r['title'] = title
    # outline the main class's methods by parsing it in memory
    mc = man.get('Main-Class')
    if mc:
        try:
            data = z.read(mc.replace('.', '/') + '.class')
            cr = _parse_class(data)
            r['functions'] = cr.get('functions', [])
            r['code_lang'] = 'java'
            r['notes'].append(f'Functions listed are the methods of the Main-Class {mc} (parsed in memory).')
        except Exception:
            pass
    r['_kw'] = [p for p, _ in pkgs.most_common(6)] + ([mc] if mc else [])


def _sniff_bad_archive(path, why):
    with open(path, 'rb') as f:
        head = f.read(16)
    return {'kind': 'binary', 'type': 'Damaged or non-standard archive',
            'notes': [f'Could not open as {why}.'], 'meta': [('First bytes', '`' + head.hex(' ') + '`')]}


# ======================================================================== rar / 7z / gz / tar
def _vint(b, p):
    v = s = 0
    while p < len(b):
        c = b[p]; p += 1
        v |= (c & 0x7f) << s
        s += 7
        if not c & 0x80:
            break
    return v, p


def _dos_dt(t):
    try:
        return datetime.datetime(((t >> 25) & 0x7f) + 1980, (t >> 21) & 0xf, (t >> 16) & 0x1f,
                                 (t >> 11) & 0x1f, (t >> 5) & 0x3f, (t & 0x1f) * 2)
    except Exception:
        return None


def _rar(path):
    size = os.path.getsize(path)
    entries, notes, ver = [], [], '?'
    with open(path, 'rb') as f:
        sig = f.read(8)
        if sig[:7] == b'Rar!\x1a\x07\x00':
            ver = 'RAR 1.5–4.x'
            pos = 7
            for _ in range(100000):
                f.seek(pos)
                h = f.read(7)
                if len(h) < 7:
                    break
                _crc, typ, flags, hsize = struct.unpack('<HBHH', h)
                if hsize < 7:
                    break
                body = f.read(hsize - 7)
                add = 0
                if typ == 0x73 and flags & 0x80:
                    notes.append('Archive headers are encrypted: file names unavailable.')
                    break
                if typ == 0x74 and len(body) >= 25:
                    pack, unp, _os, _fcrc, ftime, _uv, _meth, nlen, attr = struct.unpack('<IIBIIBBHI', body[:25])
                    off = 25
                    if flags & 0x100:
                        hp, hu = struct.unpack('<II', body[25:33]); off = 33
                        pack |= hp << 32; unp |= hu << 32
                    nm = body[off:off + nlen]
                    if flags & 0x200 and b'\x00' in nm:
                        nm = nm.split(b'\x00')[0]
                    isdir = (flags & 0xe0) == 0xe0
                    entries.append((_decode(nm).replace('\\', '/'), unp, _dos_dt(ftime), isdir, bool(flags & 4)))
                    add = pack
                elif flags & 0x8000 and len(body) >= 4:
                    add = struct.unpack('<I', body[:4])[0]
                if typ == 0x7b:
                    break
                pos += hsize + add
        elif sig == b'Rar!\x1a\x07\x01\x00':
            ver = 'RAR 5.x'
            pos = 8
            for _ in range(100000):
                f.seek(pos)
                b = f.read(4096)
                if len(b) < 6:
                    break
                hs, p = _vint(b, 4)
                hstart = p
                if hs > len(b) - hstart:
                    b += f.read(hs - (len(b) - hstart))
                typ, p = _vint(b, p)
                hfl, p = _vint(b, p)
                dsize = 0
                if hfl & 1:
                    _, p = _vint(b, p)
                if hfl & 2:
                    dsize, p = _vint(b, p)
                if typ == 4:
                    notes.append('Archive headers are encrypted: file names unavailable.')
                    break
                if typ == 2:
                    ffl, p = _vint(b, p)
                    unp, p = _vint(b, p)
                    _attr, p = _vint(b, p)
                    mt = None
                    if ffl & 2:
                        mt = datetime.datetime.fromtimestamp(struct.unpack('<I', b[p:p + 4])[0]); p += 4
                    if ffl & 4:
                        p += 4
                    _ci, p = _vint(b, p)
                    _hos, p = _vint(b, p)
                    nl, p = _vint(b, p)
                    entries.append((_decode(b[p:p + nl]), unp, mt, bool(ffl & 1), False))
                if typ == 5:
                    break
                pos = hstart + hs + dsize
        else:
            return _sniff_bad_archive(path, 'RAR (signature not found)')
    files = [e for e in entries if not e[3]]
    total = sum(e[1] for e in files)
    dates = [e[2] for e in files if e[2]]
    meta = [('Format', ver), ('Entries', f'{len(files):,} files'), ('Uncompressed size', _size(total)),
            ('Archive size', _size(size))]
    if dates:
        meta.append(('Newest entry', _wy(max(dates))))
    outline = [{'heading': f'Entries ({len(entries):,}): name · size in bytes · date'}]
    for nm, unp, dt, isdir, _ in entries[:ARCHIVE_CAP]:
        outline.append(f'`{nm}/`' if isdir else f'`{nm}` · {unp:,} · {dt:%Y-%m-%d %H:%M}' if dt
                       else f'`{nm}` · {unp:,}')
    if len(entries) > ARCHIVE_CAP:
        outline.append(f'… and {len(entries) - ARCHIVE_CAP:,} more entries')
    notes.append('Listed from RAR block headers only; no unrar available, contents not read.')
    return {'kind': 'data', 'type': 'RAR archive', 'meta': meta, 'outline': outline, 'notes': notes,
            'summary': f'RAR archive ({ver}) with {len(files):,} files, {_size(total)} uncompressed'
                       + (f', newest {max(dates):%Y-%m-%d}' if dates else '') + '.',
            'keywords': [os.path.splitext(os.path.basename(e[0]))[0] for e in files[:8]]}


def _7z(path):
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        h = f.read(32)
    if h[:6] != b"7z\xbc\xaf'\x1c":
        return _sniff_bad_archive(path, '7-Zip (signature not found)')
    meta = [('Format', f'7-Zip archive version {h[6]}.{h[7]}'), ('Archive size', _size(size))]
    return {'kind': 'data', 'type': '7-Zip archive', 'meta': meta,
            'summary': f'7-Zip archive, {_size(size)}.',
            'notes': ['No 7-Zip library installed; the (usually compressed) header listing file names was not decoded.']}


def _tar_listing(tf, limit_members=20000):
    ents = []
    for m in tf:
        ents.append(m)
        if len(ents) >= limit_members:
            break
    return ents


def _gz(path, ext):
    size = os.path.getsize(path)
    with open(path, 'rb') as f:
        h = f.read(4096)
        f.seek(max(0, size - 4))
        isize = struct.unpack('<I', f.read(4))[0] if size >= 18 else 0
    if h[:2] != b'\x1f\x8b':
        return _sniff_bad_archive(path, 'gzip (signature not found)')
    flg = h[3]
    mtime = struct.unpack('<I', h[4:8])[0]
    p = 10
    if flg & 4:
        p += 2 + struct.unpack('<H', h[10:12])[0]
    oname = ''
    if flg & 8:
        e = h.find(b'\x00', p)
        oname = _decode(h[p:e]); p = e + 1
    meta = [('Format', 'gzip (deflate)'), ('Compressed size', _size(size)),
            ('Uncompressed size (mod 4 GB)', _size(isize))]
    if oname:
        meta.append(('Original name', oname))
    if mtime:
        meta.append(('Compressed on', _ts(mtime)))
    r = {'kind': 'data', 'type': 'gzip compressed file', 'meta': meta}
    inner = oname or os.path.basename(path)[:-3]
    if ext == 'tgz' or inner.lower().endswith('.tar') or os.path.basename(path).lower().endswith('.tar.gz'):
        if size < 200 * 1024 * 1024:
            try:
                import tarfile
                with tarfile.open(path, 'r:gz') as tf:
                    return _tar_result(_tar_listing(tf), r, 'gzip-compressed tar archive')
            except Exception as e:
                r.setdefault('notes', []).append(f'tar listing failed: {type(e).__name__}')
    r['summary'] = f'gzip-compressed file{" " + oname if oname else ""}, {_size(size)} compressed ({_size(isize)} uncompressed).'
    return r


def _tar_result(ents, r, typ):
    files = [m for m in ents if m.isfile()]
    total = sum(m.size for m in files)
    newest = max((m.mtime for m in files), default=0)
    r['type'] = typ
    r['meta'] = (r.get('meta') or []) + [('Entries', f'{len(files):,} files'), ('Uncompressed size', _size(total))]
    if newest:
        r['meta'].append(('Newest entry', _ts(newest)))
    out = [{'heading': f'Entries ({len(ents):,}): name · size in bytes · date'}]
    for m in ents[:ARCHIVE_CAP]:
        if m.isdir():
            out.append(f'`{m.name}/`')
        else:
            d = datetime.datetime.fromtimestamp(m.mtime).strftime('%Y-%m-%d %H:%M') if m.mtime else '?'
            out.append(f'`{m.name}` · {m.size:,} · {d}')
    if len(ents) > ARCHIVE_CAP:
        out.append(f'… and {len(ents) - ARCHIVE_CAP:,} more entries')
    r['outline'] = out
    top = collections.Counter(m.name.split('/')[0] for m in ents)
    r['summary'] = (f'{typ[0].upper() + typ[1:]} with {len(files):,} files ({_size(total)} uncompressed)'
                    + (f'; top-level: {", ".join(t for t, _ in top.most_common(5))}' if top else '') + '.')
    r['notes'] = (r.get('notes') or []) + ['Listed from tar headers in memory; nothing extracted.']
    return r


def _tar(path):
    import tarfile
    try:
        with tarfile.open(path, 'r:') as tf:
            return _tar_result(_tar_listing(tf), {'kind': 'data'}, 'tar archive')
    except Exception as e:
        return _sniff_bad_archive(path, f'tar ({type(e).__name__})')


# ======================================================================== Java .class
_ACC_CLASS = [(0x0001, 'public'), (0x0010, 'final'), (0x0400, 'abstract')]
_ACC_MEMBER = [(0x0001, 'public'), (0x0002, 'private'), (0x0004, 'protected'), (0x0008, 'static'),
               (0x0010, 'final'), (0x0020, 'synchronized'), (0x0040, 'volatile'), (0x0080, 'transient'),
               (0x0100, 'native'), (0x0400, 'abstract'), (0x0800, 'strictfp')]
_PRIM = {'B': 'byte', 'C': 'char', 'D': 'double', 'F': 'float', 'I': 'int', 'J': 'long', 'S': 'short',
         'Z': 'boolean', 'V': 'void'}
_JAVA_VER = {45: '1.1', 46: '1.2', 47: '1.3', 48: '1.4', 49: '5', 50: '6', 51: '7', 52: '8'}


def _jtype(d, i=0):
    dims = 0
    while d[i] == '[':
        dims += 1; i += 1
    c = d[i]
    if c == 'L':
        e = d.index(';', i)
        t = d[i + 1:e].replace('/', '.')
        if t.startswith('java.lang.') and t.count('.') == 2:
            t = t[10:]
        i = e + 1
    else:
        t = _PRIM.get(c, c); i += 1
    return t + '[]' * dims, i


def _method_desc(d):
    params, i = [], 1
    while d[i] != ')':
        t, i = _jtype(d, i)
        params.append(t)
    ret, _ = _jtype(d, i + 1)
    return params, ret


def _mods(flags, table):
    return [n for b, n in table if flags & b]


def _code_calls(code, cp, cls, sup_name=('',)):
    """Walk bytecode; return referenced methods (Class.method) in order of first use."""
    L = {0x10: 2, 0x11: 3, 0x12: 2, 0x13: 3, 0x14: 3, 0x84: 3, 0xa9: 2, 0xb9: 5, 0xba: 5, 0xbc: 2, 0xc5: 4,
         0xc8: 5, 0xc9: 5}
    for o in range(0x15, 0x1a): L[o] = 2
    for o in range(0x36, 0x3b): L[o] = 2
    for o in list(range(0x99, 0xa9)) + list(range(0xb2, 0xb9)) + [0xbb, 0xbd, 0xc0, 0xc1, 0xc6, 0xc7]:
        L[o] = 3
    calls, seen, i, n = [], set(), 0, len(code)
    while i < n:
        op = code[i]
        if op == 0xaa:
            j = i + 1 + ((4 - (i + 1) % 4) % 4)
            lo, hi = struct.unpack('>ii', code[j + 4:j + 12])
            i = j + 12 + (hi - lo + 1) * 4
            continue
        if op == 0xab:
            j = i + 1 + ((4 - (i + 1) % 4) % 4)
            np_ = struct.unpack('>i', code[j + 4:j + 8])[0]
            i = j + 8 + np_ * 8
            continue
        if op == 0xc4:
            i += 6 if i + 1 < n and code[i + 1] == 0x84 else 4
            continue
        if op in (0xb6, 0xb7, 0xb8, 0xb9) and i + 2 < n:
            idx = struct.unpack('>H', code[i + 1:i + 3])[0]
            ref = cp.get(idx)
            if ref and ref[0] in (10, 11):
                c = cp_class(cp, ref[1])
                nm, _ = cp_nat(cp, ref[2])
                short = c.split('.')[-1]
                s = nm if c == cls else f'{short}.{nm}'
                if nm == '<init>':
                    s = f'new {short}' if c != cls else f'{short}()'
                    if c == sup_name[0]:
                        s = f'super() [{short}]'
                if s not in seen:
                    seen.add(s); calls.append(s)
        i += L.get(op, 1)
    return calls


def cp_utf(cp, i):
    e = cp.get(i)
    return e[1] if e and e[0] == 1 else ''


def cp_class(cp, i):
    e = cp.get(i)
    return cp_utf(cp, e[1]).replace('/', '.') if e and e[0] == 7 else ''


def cp_nat(cp, i):
    e = cp.get(i)
    return (cp_utf(cp, e[1]), cp_utf(cp, e[2])) if e and e[0] == 12 else ('', '')


def _parse_class(data):
    if data[:4] != b'\xca\xfe\xba\xbe':
        raise ValueError('not a class file')
    minor, major, cnt = struct.unpack('>HHH', data[4:10])
    p, cp, i = 10, {}, 1
    while i < cnt:
        t = data[p]
        if t == 1:
            ln = struct.unpack('>H', data[p + 1:p + 3])[0]
            cp[i] = (1, data[p + 3:p + 3 + ln].decode('utf-8', 'replace')); p += 3 + ln
        elif t in (3, 4):
            cp[i] = (t, data[p + 1:p + 5]); p += 5
        elif t in (5, 6):
            cp[i] = (t, data[p + 1:p + 9]); p += 9; i += 1
        elif t in (7, 8, 16, 19, 20):
            cp[i] = (t, struct.unpack('>H', data[p + 1:p + 3])[0]); p += 3
        elif t in (9, 10, 11, 12, 17, 18):
            a, b = struct.unpack('>HH', data[p + 1:p + 5]); cp[i] = (t, a, b); p += 5
        elif t == 15:
            cp[i] = (t, data[p + 1], struct.unpack('>H', data[p + 2:p + 4])[0]); p += 4
        else:
            raise ValueError(f'bad constant tag {t}')
        i += 1
    acc, this, sup, nif = struct.unpack('>HHHH', data[p:p + 8]); p += 8
    cls = cp_class(cp, this)
    supn = cp_class(cp, sup) if sup else ''
    ifs = [cp_class(cp, struct.unpack('>H', data[p + 2 * k:p + 2 * k + 2])[0]) for k in range(nif)]
    p += 2 * nif

    def attrs(p):
        n = struct.unpack('>H', data[p:p + 2])[0]; p += 2
        out = {}
        for _ in range(n):
            ni, ln = struct.unpack('>HI', data[p:p + 6])
            out.setdefault(cp_utf(cp, ni), data[p + 6:p + 6 + ln]); p += 6 + ln
        return out, p

    def members(p):
        n = struct.unpack('>H', data[p:p + 2])[0]; p += 2
        out = []
        for _ in range(n):
            fa, ni, di = struct.unpack('>HHH', data[p:p + 6])
            at, p = attrs(p + 6)
            out.append((fa, cp_utf(cp, ni), cp_utf(cp, di), at))
        return out, p

    fields, p = members(p)
    methods, p = members(p)
    cattrs, p = attrs(p)
    short = cls.split('.')[-1]
    pkg = '.'.join(cls.split('.')[:-1])
    src = cp_utf(cp, struct.unpack('>H', cattrs['SourceFile'][:2])[0]) if 'SourceFile' in cattrs else ''
    is_if = bool(acc & 0x0200)
    kindword = 'enum' if acc & 0x4000 else ('@interface' if acc & 0x2000 else ('interface' if is_if else 'class'))
    cmods = _mods(acc, _ACC_CLASS)
    if is_if and 'abstract' in cmods:
        cmods.remove('abstract')
    decl = ' '.join(cmods + [kindword, short])
    if supn and supn != 'java.lang.Object' and not is_if:
        decl += ' extends ' + supn
    if ifs:
        decl += (' extends ' if is_if else ' implements ') + ', '.join(ifs)
    outline = [{'heading': 'Class'}, f'`{decl}`']
    if fields:
        outline.append({'heading': f'Fields ({len(fields)})'})
        for fa, nm, de, at in fields:
            if fa & 0x1000:
                continue
            t, _ = _jtype(de)
            val = ''
            if 'ConstantValue' in at:
                e = cp.get(struct.unpack('>H', at['ConstantValue'][:2])[0])
                if e:
                    if e[0] == 3: val = str(struct.unpack('>i', e[1])[0])
                    elif e[0] == 4: val = repr(struct.unpack('>f', e[1])[0])
                    elif e[0] == 5: val = str(struct.unpack('>q', e[1])[0]) + 'L'
                    elif e[0] == 6: val = repr(struct.unpack('>d', e[1])[0])
                    elif e[0] == 8: val = '"' + cp_utf(cp, e[1])[:80] + '"'
            outline.append(f'`{" ".join(_mods(fa, _ACC_MEMBER) + [t, nm])}{" = " + val if val else ""}`')
    funcs = []
    for fa, nm, de, at in methods:
        if fa & 0x1000 or nm == '<clinit>' and False:
            continue
        try:
            ps, ret = _method_desc(de)
        except Exception:
            ps, ret = [], '?'
        disp = short if nm == '<init>' else ('static initializer' if nm == '<clinit>' else nm)
        mods = _mods(fa & ~0x0040 & ~0x0080, _ACC_MEMBER)
        if fa & 0x0080:
            ps_disp = ps[:-1] + [ps[-1][:-2] + '...'] if ps and ps[-1].endswith('[]') else ps
        else:
            ps_disp = ps
        pnames = [f'arg{k}' for k in range(len(ps))]
        line, calls, throws = '', [], []
        code = at.get('Code')
        if code:
            try:
                clen = struct.unpack('>I', code[4:8])[0]
                bc = code[8:8 + clen]
                calls = _code_calls(bc, cp, cls, (supn,)) if nm == '<init>' else _code_calls(bc, cp, cls)
                q = 8 + clen
                elen = struct.unpack('>H', code[q:q + 2])[0]; q += 2 + 8 * elen
                na = struct.unpack('>H', code[q:q + 2])[0]; q += 2
                for _ in range(na):
                    ani, aln = struct.unpack('>HI', code[q:q + 6])
                    an, body = cp_utf(cp, ani), code[q + 6:q + 6 + aln]
                    if an == 'LineNumberTable':
                        k = struct.unpack('>H', body[:2])[0]
                        lines = [struct.unpack('>HH', body[2 + 4 * j:6 + 4 * j])[1] for j in range(k)]
                        if lines:
                            line = min(lines)
                    elif an == 'LocalVariableTable':
                        k = struct.unpack('>H', body[:2])[0]
                        slots = {}
                        for j in range(k):
                            sp, _l, ni, _di, ix = struct.unpack('>HHHHH', body[2 + 10 * j:12 + 10 * j])
                            if sp == 0:
                                slots[ix] = cp_utf(cp, ni)
                        s = 0 if fa & 0x0008 else 1
                        for k2, t in enumerate(ps):
                            if s in slots:
                                pnames[k2] = slots[s]
                            s += 2 if t in ('long', 'double') else 1
                    q += 6 + aln
            except Exception:
                pass
        if 'MethodParameters' in at:
            try:
                b = at['MethodParameters']
                for k in range(min(b[0], len(ps))):
                    ni = struct.unpack('>H', b[1 + 4 * k:3 + 4 * k])[0]
                    if ni:
                        pnames[k] = cp_utf(cp, ni)
            except Exception:
                pass
        if 'Exceptions' in at:
            b = at['Exceptions']
            k = struct.unpack('>H', b[:2])[0]
            throws = [cp_class(cp, struct.unpack('>H', b[2 + 2 * j:4 + 2 * j])[0]).split('.')[-1] for j in range(k)]
        sig = ' '.join(mods + ([] if nm in ('<init>', '<clinit>') else [ret]) + [disp]) if nm != '<clinit>' else 'static { … }'
        if nm != '<clinit>':
            sig += '(' + ', '.join(f'{t} {n}' for t, n in zip(ps_disp, pnames)) + ')'
            if throws:
                sig += ' throws ' + ', '.join(throws)
        funcs.append({'name': disp, 'kind': 'constructor' if nm == '<init>' else 'method', 'line': line,
                      'signature': sig, 'params': [(n, t, '') for t, n in zip(ps_disp, pnames)],
                      'returns': '' if nm in ('<init>', '<clinit>') else ret, 'calls': calls,
                      'doc': ('Abstract/interface method (no body).' if not code and not fa & 0x0100 else
                              'Native method.' if fa & 0x0100 else '')})
    meta = [('Class', cls), ('Package', pkg or '(default)'), ('Kind', kindword)]
    if supn:
        meta.append(('Superclass', supn))
    if ifs:
        meta.append(('Interfaces', ', '.join(ifs)))
    if src:
        meta.append(('Compiled from', src))
    meta.append(('Class-file version', f'{major}.{minor}' + (f' (Java {_JAVA_VER[major]})' if major in _JAVA_VER else
                                                           f' (Java {major - 44})' if major > 52 else '')))
    meta.append(('Members', f'{len(methods)} methods, {len(fields)} fields, {cnt - 1} constant-pool slots'))
    strs = [cp_utf(cp, e[1]) for e in cp.values() if e[0] == 8]
    strs = [s for s in dict.fromkeys(strs) if s.strip()]
    pars = []
    if strs:
        pars.append({'heading': f'String constants ({len(strs)})'})
        pars.extend(strs[:2000])
    pub = [f['name'] for f in funcs if f['kind'] == 'method']
    nctor = sum(1 for f in funcs if f['kind'] == 'constructor')
    summ = (f'Compiled Java {kindword} {cls}' + (f' (from {src})' if src else '')
            + (f', extends {supn.split(".")[-1]}' if supn and supn != 'java.lang.Object' else '')
            + (f', implements {", ".join(x.split(".")[-1] for x in ifs)}' if ifs and not is_if else '')
            + (f'; {_pl(nctor, "constructor")}' if nctor else '')
            + f'; {_pl(len(pub), "method")}' + (': ' + ', '.join(pub[:15]) + (' …' if len(pub) > 15 else '') if pub else '')
            + '.')
    return {'kind': 'source', 'type': 'Java class file (bytecode)', 'title': cls, 'meta': meta,
            'outline': outline, 'functions': funcs, 'code_lang': 'java', 'paragraphs': pars,
            'summary': summ, 'keywords': [short, pkg] + ([supn.split('.')[-1]] if supn else []) + pub[:8]}


def _class(path):
    with open(path, 'rb') as f:
        data = f.read(16 * 1024 * 1024)
    try:
        return _parse_class(data)
    except Exception as e:
        return {'kind': 'binary', 'type': 'Java class file (unparseable)',
                'notes': [f'Class-file parse failed: {type(e).__name__}: {str(e)[:100]}'],
                'paragraphs': _strings_pars(_strings(data))}


# ======================================================================== images
_EXIF = {0x010f: 'Camera make', 0x0110: 'Camera model', 0x0131: 'Software', 0x013b: 'Artist',
         0x8298: 'Copyright', 0x010e: 'Description', 0x0132: 'Date/time', 0x9003: 'Date taken',
         0x0112: 'Orientation'}


def _image(path, ext):
    if ext == 'svg':
        return _svg(path)
    if ext == 'wpg':
        return _wpg(path)
    try:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
    except Exception:
        return {'kind': 'binary', 'type': f'{ext.upper()} image', 'notes': ['PIL not available.']}
    import warnings
    warnings.filterwarnings('ignore')
    meta, notes, pars = [], [], []
    try:
        im = Image.open(path)
    except Exception as e:
        with open(path, 'rb') as f:
            head = f.read(16)
        return {'kind': 'binary', 'type': f'{ext.upper()} image (unreadable)',
                'notes': [f'PIL could not open it: {type(e).__name__}: {str(e)[:100]}'],
                'meta': [('First bytes', '`' + head.hex(' ') + '`')]}
    with im:
        fmt = im.format or ext.upper()
        if fmt == 'WMF' and ext == 'emf':
            fmt = 'EMF'
        w, h = im.size
        meta += [('Format', f'{fmt}' + (f' — {im.format_description}' if getattr(im, 'format_description', '') else '')),
                 ('Dimensions', f'{w} × {h} px'), ('Colour mode', im.mode)]
        dpi = im.info.get('dpi')
        if dpi:
            try:
                dx, dy = float(dpi[0]), float(dpi[1])
                if dx > 1:
                    meta.append(('Resolution', f'{dx:.0f} × {dy:.0f} dpi' + (f' ({w / dx:.2f} × {h / dy:.2f} in)')))
            except Exception:
                pass
        if fmt in ('GIF', 'TIFF', 'ICO', 'PNG') and os.path.getsize(path) < 50 * 1024 * 1024:
            try:
                nf = getattr(im, 'n_frames', 1)
                if nf > 1:
                    meta.append(('Frames', nf))
            except Exception:
                pass
        if fmt == 'ICO':
            try:
                meta.append(('Icon sizes', ', '.join(f'{a}×{b}' for a, b in sorted(im.info.get('sizes', [])))))
            except Exception:
                pass
        for k in ('compression', 'interlace', 'progressive', 'transparency', 'gamma', 'version', 'loop', 'duration'):
            if k in im.info and not isinstance(im.info[k], (bytes, tuple, dict)):
                meta.append((k.capitalize(), im.info[k]))
        date = None
        try:
            ex = im.getexif()
            items = dict(ex)
            try:
                items.update(ex.get_ifd(0x8769))
            except Exception:
                pass
            for tag, label in _EXIF.items():
                v = items.get(tag)
                if v not in (None, '', b''):
                    if isinstance(v, bytes):
                        v = _decode(v).strip('\x00 ')
                    v = str(v).strip('\x00 ')[:200]
                    if v:
                        meta.append((label, v))
                        if tag in (0x9003, 0x0132) and not date:
                            date = v
        except Exception:
            pass
        if fmt == 'TIFF':
            try:
                for tag, label in ((270, 'Description'), (305, 'Software'), (306, 'Date/time'), (315, 'Artist')):
                    v = im.tag_v2.get(tag)
                    if v and label not in dict(meta):
                        meta.append((label, str(v)[:200]))
            except Exception:
                pass
        for k, v in im.info.items():
            if isinstance(v, str) and k.lower() not in ('icc_profile',) and len(v) > 0 and k not in ('dpi',):
                if k.lower() in ('comment', 'description', 'title', 'author', 'software', 'creation time',
                                 'copyright', 'source', 'xml:com.adobe.xmp') or fmt == 'PNG':
                    if k.lower().startswith('xml:com.adobe.xmp'):
                        t = re.findall(r'<(?:xmp:CreatorTool|dc:title|dc:creator)[^>]*>(.*?)<', v, re.S)
                        if t:
                            meta.append(('XMP', '; '.join(x.strip() for x in t if x.strip())[:200]))
                        continue
                    pars.append(f'{k}: {v}'[:5000])
            elif isinstance(v, bytes) and k == 'comment':
                pars.append('Comment: ' + _decode(v)[:5000])
        if 'icc_profile' in im.info:
            meta.append(('ICC profile', 'embedded'))
    notes.append('Image: no OCR performed; any text in the picture is not transcribed.')
    base = os.path.splitext(os.path.basename(path))[0]
    summ = f'{fmt} image {w}×{h} px, {im.mode}'
    if date:
        summ += f', taken/saved {date}'
    cam = dict(meta).get('Camera model')
    if cam:
        summ += f', {cam}'
    summ += '.'
    if pars:
        summ += ' Embedded text: ' + pars[0][:200]
    return {'kind': 'binary', 'type': f'{fmt} image', 'meta': meta, 'notes': notes, 'paragraphs': pars,
            'summary': summ, 'keywords': [w for w in re.split(r'[\s_\-]+', base) if len(w) > 2][:5]}


def _svg(path):
    text, _ = _read_text(path)
    meta, pars, title = [], [], ''
    m = re.search(r'<svg\b([^>]*)>', text, re.S | re.I)
    if m:
        for a in ('width', 'height', 'viewBox'):
            mm = re.search(r'\b' + a + r'\s*=\s*["\']([^"\']*)', m.group(1))
            if mm:
                meta.append((a, mm.group(1)))
    mm = re.search(r'<title[^>]*>(.*?)</title>', text, re.S | re.I)
    if mm:
        title = re.sub(r'\s+', ' ', mm.group(1)).strip()
    mm = re.search(r'<desc[^>]*>(.*?)</desc>', text, re.S | re.I)
    if mm:
        pars.append(re.sub(r'\s+', ' ', mm.group(1)).strip())
    gen = re.search(r'<!--\s*(Generator:[^>]*?)-->', text)
    if gen:
        meta.append(('Generator', gen.group(1).strip()))
    import html
    for t in re.findall(r'<text\b[^>]*>(.*?)</text>', text, re.S | re.I)[:3000]:
        t = html.unescape(re.sub(r'<[^>]+>', ' ', t))
        t = re.sub(r'\s+', ' ', t).strip()
        if t:
            pars.append(t)
    n_el = len(re.findall(r'<(?:path|rect|circle|line|polyline|polygon|ellipse)\b', text))
    meta.append(('Shape elements', n_el))
    return {'kind': 'document', 'type': 'SVG vector image', 'title': title, 'meta': meta, 'paragraphs': pars,
            'summary': f'SVG vector drawing{" “" + title + "”" if title else ""}'
                       + (f' ({dict(meta).get("width")}×{dict(meta).get("height")})' if 'width' in dict(meta) else '')
                       + f' with {n_el} shapes and {len(pars)} text elements.'}


def _wpg(path):
    with open(path, 'rb') as f:
        h = f.read(16)
        data = f.read(2 * 1024 * 1024)
    meta = [('First bytes', '`' + h.hex(' ') + '`')]
    typ = 'WordPerfect Graphics (WPG)'
    if h[:4] == b'\xffWPC':
        meta = [('Format', f'WordPerfect Graphics, file type {h[9]}, version {h[10]}.{h[11]}')]
    strs = _strings(data, 5, 300)
    return {'kind': 'binary', 'type': typ, 'meta': meta, 'paragraphs': _strings_pars(strs),
            'summary': f'{typ} vector/bitmap image.',
            'notes': ['WPG is not decoded; printable strings shown if any.'] if strs else ['WPG is not decoded.']}


# ======================================================================== audio / video
def _riff_info(f, end):
    """Parse a LIST/INFO body from current position to `end` -> list of (label, value)."""
    labels = {b'INAM': 'Title', b'IART': 'Artist', b'ICMT': 'Comment', b'ICRD': 'Date', b'ISFT': 'Software',
              b'IPRD': 'Product', b'ICOP': 'Copyright', b'IENG': 'Engineer', b'IGNR': 'Genre', b'ISBJ': 'Subject'}
    out = []
    while f.tell() + 8 <= end:
        cid, ln = struct.unpack('<4sI', f.read(8))
        v = f.read(ln)
        if ln & 1:
            f.read(1)
        if cid in labels:
            s = _decode(v).strip('\x00 ')
            if s:
                out.append((labels[cid], s[:300]))
    return out


_WAVE_FMT = {1: 'PCM', 2: 'Microsoft ADPCM', 3: 'IEEE float', 6: 'A-law', 7: 'µ-law', 0x11: 'IMA ADPCM',
             0x50: 'MPEG', 0x55: 'MPEG Layer 3', 0xfffe: 'WAVE_FORMAT_EXTENSIBLE'}


def _riff(path):
    size = os.path.getsize(path)
    meta, info, notes = [], [], []
    with open(path, 'rb') as f:
        h = f.read(12)
        if h[:4] not in (b'RIFF', b'RIFX') or len(h) < 12:
            return None
        form = h[8:12]
        fmt = None; data_len = 0; avih = None; strh = []
        pos = 12
        for _ in range(10000):
            f.seek(pos)
            ch = f.read(8)
            if len(ch) < 8:
                break
            cid, ln = struct.unpack('<4sI', ch)
            body_pos = pos + 8
            if cid == b'fmt ':
                fmt = f.read(min(ln, 40))
            elif cid == b'data':
                data_len = ln
            elif cid == b'LIST':
                lt = f.read(4)
                if lt == b'INFO':
                    info += _riff_info(f, body_pos + ln)
                elif lt == b'hdrl' and form == b'AVI ':
                    # walk inside hdrl for avih and strl/strh
                    sub = f.read(min(ln - 4, 65536))
                    k = 0
                    while k + 8 <= len(sub):
                        sid, sl = struct.unpack('<4sI', sub[k:k + 8])
                        if sid == b'avih':
                            avih = sub[k + 8:k + 8 + 56]
                        if sid == b'LIST':
                            k += 12; continue
                        if sid == b'strh':
                            strh.append(sub[k + 8:k + 8 + 56])
                        k += 8 + sl + (sl & 1)
                elif lt == b'movi':
                    pass
            pos = body_pos + ln + (ln & 1)
            if ln == 0 and cid == b'\x00\x00\x00\x00':
                break
    if form == b'WAVE':
        typ = 'WAV audio'
        if fmt and len(fmt) >= 16:
            tag, ch, sr, br, ba, bits = struct.unpack('<HHIIHH', fmt[:16])
            meta += [('Encoding', _WAVE_FMT.get(tag, f'format 0x{tag:04x}')), ('Channels', ch),
                     ('Sample rate', f'{sr:,} Hz'), ('Bits per sample', bits), ('Byte rate', f'{br:,} B/s')]
            dur = data_len / br if br else 0
            if dur:
                meta.append(('Duration', _dur(dur)))
            summ = (f'WAV audio, {_WAVE_FMT.get(tag, "format " + str(tag))} {ch}-channel '
                    f'{sr / 1000:g} kHz {bits}-bit' + (f', {dur:.1f} s' if dur else '') + '.')
        else:
            summ = 'WAV audio (no fmt chunk found).'
    elif form == b'AVI ':
        typ = 'AVI video'
        summ = 'AVI video.'
        if avih and len(avih) >= 40:
            usf, _mbps, _pg, _fl, frames, _if, streams, _buf, w, hh = struct.unpack('<10I', avih[:40])
            fps = 1e6 / usf if usf else 0
            meta += [('Dimensions', f'{w} × {hh} px'), ('Frames', f'{frames:,}'), ('Streams', streams)]
            if fps:
                meta += [('Frame rate', f'{fps:.3f} fps'), ('Duration', _dur(frames / fps))]
            summ = f'AVI video {w}×{hh}' + (f', {fps:.2f} fps, {frames / fps:.1f} s' if fps else '') + '.'
        for s in strh:
            if len(s) >= 8:
                st = {b'vids': 'video', b'auds': 'audio', b'txts': 'text', b'mids': 'MIDI'}.get(s[:4], s[:4].decode('latin-1'))
                cc = s[4:8].decode('latin-1').strip('\x00 ')
                meta.append(('Stream', f'{st}' + (f', codec {cc!r}' if cc else '')))
    else:
        typ = f'RIFF {form.decode("latin-1").strip()} file'
        summ = f'{typ}.'
    meta += info
    if size > 0:
        meta.append(('File size', _size(size)))
    pars = [f'{k}: {v}' for k, v in info if k in ('Title', 'Comment', 'Subject')]
    return {'kind': 'binary', 'type': typ, 'meta': meta, 'summary': summ, 'paragraphs': pars, 'notes': notes}


def _wav(path):
    r = None
    try:
        r = _riff(path)
    except Exception:
        r = None
    if r:
        return r
    try:
        import wave
        with wave.open(path, 'rb') as w:
            ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        return {'kind': 'binary', 'type': 'WAV audio',
                'meta': [('Channels', ch), ('Sample rate', f'{sr} Hz'), ('Bits per sample', sw * 8),
                         ('Duration', _dur(n / sr if sr else 0))],
                'summary': f'WAV audio, {ch}-channel {sr / 1000:g} kHz {sw * 8}-bit, {n / sr if sr else 0:.1f} s.'}
    except Exception as e:
        return {'kind': 'binary', 'type': 'WAV audio (unreadable)', 'notes': [f'{type(e).__name__}: {e}'[:150]]}


def _mp4(path):
    size = os.path.getsize(path)
    meta, tracks, tags = [], [], {}
    brand = ''
    dur = 0

    def walk(f, start, end, depth, ctx):
        nonlocal brand, dur
        p = start
        while p + 8 <= end and depth < 12:
            f.seek(p)
            h = f.read(8)
            if len(h) < 8:
                return
            ln, typ = struct.unpack('>I4s', h)
            hl = 8
            if ln == 1:
                ln = struct.unpack('>Q', f.read(8))[0]; hl = 16
            elif ln == 0:
                ln = end - p
            if ln < hl:
                return
            body = p + hl
            if typ == b'ftyp':
                brand = f.read(4).decode('latin-1')
            elif typ in (b'moov', b'trak', b'mdia', b'minf', b'stbl', b'udta', b'ilst', b'edts'):
                sub = ctx
                if typ == b'trak':
                    sub = {}
                    tracks.append(sub)
                elif typ == b'udta':
                    sub = None
                walk(f, body, p + ln, depth + 1, sub)
            elif typ == b'meta':
                walk(f, body + 4, p + ln, depth + 1, None)
            elif typ == b'mvhd':
                b = f.read(32)
                if b[0] == 1:
                    ts, d = struct.unpack('>IQ', b[20:32])
                else:
                    ts, d = struct.unpack('>II', b[12:20])
                if ts:
                    dur = d / ts
            elif typ == b'tkhd':
                b = f.read(92)
                off = 76 if b[0] == 0 else 88
                if len(b) >= off + 8 and ctx is not None:
                    w, hh = struct.unpack('>II', b[off:off + 8])
                    ctx['dims'] = (w >> 16, hh >> 16)
            elif typ == b'mdhd' and ctx is not None:
                b = f.read(32)
                if b[0] == 1:
                    ts, d = struct.unpack('>IQ', b[20:32])
                else:
                    ts, d = struct.unpack('>II', b[12:20])
                ctx['dur'] = d / ts if ts else 0
                ctx['ts'] = ts
            elif typ == b'hdlr' and ctx is not None and 'handler' not in ctx:
                b = f.read(12)
                ctx['handler'] = b[8:12].decode('latin-1')
            elif typ == b'stsd' and ctx is not None:
                b = f.read(16)
                ctx['codec'] = b[12:16].decode('latin-1')
                if ctx.get('handler') == 'soun':
                    b2 = f.read(28)
                    if len(b2) >= 28:
                        ctx['ch'], ctx['bits'] = struct.unpack('>HH', b2[16:20])
                        ctx['sr'] = struct.unpack('>I', b2[24:28])[0] >> 16
            elif depth >= 1 and typ[:1] == b'\xa9' or typ in (b'aART', b'desc', b'cprt'):
                b = f.read(min(ln - hl, 4096))
                k = b.find(b'data')
                if k >= 4:
                    tags[typ.decode('latin-1')] = _decode(b[k + 12:]).strip('\x00 ')[:300]
            p += ln

    with open(path, 'rb') as f:
        walk(f, 0, size, 0, None)
    names = {'©nam': 'Title', '©ART': 'Artist', '©alb': 'Album', '©day': 'Date', '©too': 'Encoder',
             '©cmt': 'Comment', 'aART': 'Album artist', '©wrt': 'Composer', 'desc': 'Description'}
    meta.append(('Brand', brand or '?'))
    if dur:
        meta.append(('Duration', _dur(dur)))
    vid = None
    for t in tracks:
        hd = {'vide': 'video', 'soun': 'audio', 'text': 'text', 'sbtl': 'subtitle', 'tmcd': 'timecode'}.get(
            t.get('handler'), t.get('handler', '?'))
        s = f'{hd} track, codec {t.get("codec", "?")!r}'
        if hd == 'video' and t.get('dims'):
            s += f', {t["dims"][0]}×{t["dims"][1]}'; vid = vid or t
        if hd == 'audio' and t.get('sr'):
            s += f', {t.get("ch")} ch {t["sr"]} Hz'
        if t.get('dur'):
            s += f', {t["dur"]:.2f} s'
        meta.append(('Track', s))
    for k, v in tags.items():
        meta.append((names.get(k, k), v))
    ext = path.rsplit('.', 1)[-1].lower()
    kind = 'QuickTime movie' if ext == 'mov' or brand.startswith('qt') else (
        'MPEG-4 audio' if ext == 'm4a' or (not vid and tracks) else 'MPEG-4 video')
    summ = kind + (f' {vid["dims"][0]}×{vid["dims"][1]}' if vid and vid.get('dims') else '') + \
        (f', {dur:.1f} s' if dur else '') + (f', “{tags["©nam"]}”' if '©nam' in tags else '') + '.'
    return {'kind': 'binary', 'type': kind, 'meta': meta, 'summary': summ,
            'title': tags.get('©nam', ''),
            'paragraphs': [f'{names.get(k, k)}: {v}' for k, v in tags.items() if k in ('©cmt', 'desc', '©lyr')]}


_MP3_BR = {1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
           2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]}
_MP3_SR = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def _mp3(path):
    size = os.path.getsize(path)
    meta, tags = [], {}
    with open(path, 'rb') as f:
        h = f.read(10)
        start = 0
        if h[:3] == b'ID3':
            tsz = (h[6] << 21) | (h[7] << 14) | (h[8] << 7) | h[9]
            start = 10 + tsz
            body = f.read(min(tsz, 1 << 20))
            ver = h[3]
            meta.append(('ID3 tag', f'v2.{ver}'))
            p = 0
            while p + 10 <= len(body) and ver >= 3:
                fid = body[p:p + 4]
                if not fid.strip(b'\x00'):
                    break
                fl = struct.unpack('>I', body[p + 4:p + 8])[0]
                if ver == 4:
                    fl = ((fl >> 24) & 0x7f) << 21 | ((fl >> 16) & 0x7f) << 14 | ((fl >> 8) & 0x7f) << 7 | (fl & 0x7f)
                v = body[p + 10:p + 10 + fl]
                if fid[:1] == b'T' or fid == b'COMM':
                    enc = v[:1]
                    s = v[1:]
                    if fid == b'COMM':
                        s = s[3:]
                    try:
                        s = s.decode({b'\x01': 'utf-16', b'\x02': 'utf-16-be', b'\x03': 'utf-8'}.get(enc, 'latin-1'))
                    except Exception:
                        s = _decode(s)
                    s = s.replace('\x00', ' ').strip()
                    if s:
                        tags[fid.decode('latin-1')] = s[:300]
                p += 10 + fl
        f.seek(start)
        buf = f.read(8192)
        f.seek(max(0, size - 128))
        tail = f.read(128)
    if tail[:3] == b'TAG':
        for k, a, b in (('TIT2', 3, 33), ('TPE1', 33, 63), ('TALB', 63, 93), ('TYER', 93, 97)):
            v = _decode(tail[a:b]).strip('\x00 ')
            if v:
                tags.setdefault(k, v)
    dur = 0
    for i in range(len(buf) - 4):
        if buf[i] == 0xff and buf[i + 1] & 0xe0 == 0xe0:
            b1, b2, b3 = buf[i + 1], buf[i + 2], buf[i + 3]
            verb, layer, bri, sri = (b1 >> 3) & 3, (b1 >> 1) & 3, b2 >> 4, (b2 >> 2) & 3
            if verb == 1 or layer != 1 or bri in (0, 15) or sri == 3:
                continue
            br = _MP3_BR[1 if verb == 3 else 2][bri]
            sr = _MP3_SR[verb][sri]
            ch = 'mono' if (b3 >> 6) == 3 else 'stereo'
            meta += [('Encoding', f'MPEG-{ {3: "1", 2: "2", 0: "2.5"}[verb]} Layer III'),
                     ('Bitrate (first frame)', f'{br} kbit/s'), ('Sample rate', f'{sr} Hz'), ('Channels', ch)]
            dur = (size - start) * 8 / (br * 1000) if br else 0
            if dur:
                meta.append(('Duration (CBR estimate)', _dur(dur)))
            break
    names = {'TIT2': 'Title', 'TPE1': 'Artist', 'TALB': 'Album', 'TYER': 'Year', 'TDRC': 'Date',
             'COMM': 'Comment', 'TCON': 'Genre', 'TENC': 'Encoded by', 'TSSE': 'Encoder'}
    for k, v in tags.items():
        meta.append((names.get(k, k), v))
    t = tags.get('TIT2', '')
    return {'kind': 'binary', 'type': 'MP3 audio', 'meta': meta, 'title': t,
            'summary': 'MP3 audio' + (f' “{t}”' if t else '') + (f' by {tags["TPE1"]}' if 'TPE1' in tags else '')
                       + (f', {dur:.0f} s' if dur else '') + '.',
            'paragraphs': [f'Comment: {tags["COMM"]}'] if 'COMM' in tags else []}


def _wma(path):
    HDR = bytes.fromhex('3026b2758e66cf11a6d900aa0062ce6c')
    FILEP = bytes.fromhex('a1dcab8c47a9cf118ee400c00c205365')
    CDESC = bytes.fromhex('3326b2758e66cf11a6d900aa0062ce6c')
    with open(path, 'rb') as f:
        h = f.read(30)
        if h[:16] != HDR:
            return {'kind': 'binary', 'type': 'WMA/ASF (unrecognised)'}
        hsize = struct.unpack('<Q', h[16:24])[0]
        body = f.read(min(hsize, 1 << 20) - 30)
    meta, title = [], ''
    p = 0
    while p + 24 <= len(body):
        gid, ln = body[p:p + 16], struct.unpack('<Q', body[p + 16:p + 24])[0]
        if ln < 24:
            break
        o = body[p + 24:p + ln]
        if gid == FILEP and len(o) >= 64:
            ct = struct.unpack('<Q', o[24:32])[0]
            play, _send, preroll = struct.unpack('<QQQ', o[40:64])
            d = play / 1e7 - preroll / 1000
            meta.append(('Duration', _dur(d)))
            try:
                meta.append(('Created', _wy(datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=ct / 10))))
            except Exception:
                pass
        elif gid == CDESC and len(o) >= 10:
            lens = struct.unpack('<5H', o[:10])
            q = 10
            for lab, l in zip(('Title', 'Author', 'Copyright', 'Description', 'Rating'), lens):
                s = o[q:q + l].decode('utf-16-le', 'replace').strip('\x00 ')
                q += l
                if s:
                    meta.append((lab, s[:300]))
                    if lab == 'Title':
                        title = s
        p += ln
    return {'kind': 'binary', 'type': 'Windows Media (ASF/WMA) audio', 'meta': meta, 'title': title,
            'summary': 'Windows Media audio' + (f' “{title}”' if title else '')
                       + (f', {dict(meta)["Duration"]}' if 'Duration' in dict(meta) else '') + '.'}


# ======================================================================== scripts
def _comment_blocks(lines, prefixes):
    """Group consecutive comment lines into paragraphs. Returns [(start_line, text)]."""
    blocks, cur, start = [], [], 0
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        c = None
        for pf in prefixes:
            if pf.match(s):
                c = pf.sub('', s, count=1)
                break
        if c is not None:
            if not cur:
                start = i
            cur.append(c.rstrip())
        else:
            if cur:
                blocks.append((start, cur))
            cur = []
    if cur:
        blocks.append((start, cur))
    out = []
    for st, b in blocks:
        txt = '\n'.join(x for x in b).strip('\n')
        txt = re.sub(r'^[\s#=\-\*~_/]+$', '', txt, flags=re.M).strip()
        if txt:
            out.append((st, txt))
    return out


def _doc_before(lines, idx, rx):
    """Comment lines directly above line index idx (0-based)."""
    doc = []
    j = idx - 1
    while j >= 0:
        s = lines[j].strip()
        if rx.match(s):
            doc.insert(0, rx.sub('', s, count=1).strip())
            j -= 1
        else:
            break
    t = '\n'.join(d for d in doc if not re.fullmatch(r'[#=\-\*~_/ ]*', d)).strip()
    return t


def _body(lines, i, end, cap=40):
    seg = lines[i:end]
    while seg and not seg[-1].strip():
        seg.pop()
    if len(seg) > cap:
        seg = seg[:cap] + [f'… ({len(lines[i:end]) - cap} more lines)']
    return '\n'.join(seg)


_SH_CMD = re.compile(r'^\s*(?:sudo\s+|exec\s+|then\s+|do\s+|else\s+)?([A-Za-z_./][\w./\-+]*)')
_SH_KW = {'if', 'then', 'else', 'elif', 'fi', 'for', 'while', 'do', 'done', 'case', 'esac', 'in', 'function',
          'return', 'local', 'export', 'set', 'shift', 'break', 'continue', 'until', 'true', 'false', 'exit',
          'readonly', 'declare', 'unset', '{', '}', 'trap', 'eval'}


_LICENSE = re.compile(r'(?i)\b(copyright|all rights reserved|disclaimer|warrant|licen[cs]e|permission is hereby|'
                      r'redistribut|general public|confidential and proprietary)\b')


def _first_comment_summary(blocks, skip_shebang=True):
    lic = ''
    for st, t in blocks[:6]:
        keep = []
        for x in t.split('\n'):
            if x.startswith('!'):
                continue
            letters = sum(c.isalpha() for c in x)
            if letters < 3 or letters < len(x.strip()) * 0.35:
                continue
            keep.append(x)
        t2 = '\n'.join(keep)
        if len(_LICENSE.findall(t2)) >= 2 or (len(t2) > 300 and _LICENSE.search(t2)):
            lic = lic or re.sub(r'\s+', ' ', t2).strip()
            continue
        t2 = re.sub(r'\s+', ' ', t2).strip()
        if len(t2) >= 12 and sum(c.isalpha() for c in t2) > len(t2) * 0.5:
            return t2[:600]
    return lic[:300]


def _shell(path, text, typ='Shell script'):
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    crx = re.compile(r'^(?!#!)#+\s?')
    blocks = _comment_blocks(lines, [crx])
    starts = []
    fre = re.compile(r'^\s*(?:function\s+([A-Za-z_][\w:.\-]*)\s*(?:\(\s*\))?|([A-Za-z_][\w:.\-]*)\s*\(\s*\))\s*\{?\s*$')
    for i, ln in enumerate(lines):
        m = fre.match(ln)
        if m:
            starts.append((i, m.group(1) or m.group(2)))
    fnames = {n for _, n in starts}
    funcs = []
    for k, (i, n) in enumerate(starts):
        # body ends at the first line that is exactly '}' at column 0 or next function
        end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
        for j in range(i + 1, end):
            if re.match(r'^\}\s*$', lines[j]):
                end = j + 1
                break
        calls = []
        for ln in lines[i + 1:end]:
            for part in re.split(r'[;&|]+|\$\(|`', ln):
                mm = _SH_CMD.match(part)
                if mm and not part.strip().startswith('#'):
                    c = mm.group(1)
                    if c not in _SH_KW and '=' not in part.split()[0] and c not in calls:
                        calls.append(c)
        calls.sort(key=lambda c: c not in fnames)
        funcs.append({'name': n, 'kind': 'shell function', 'line': i + 1, 'signature': _body(lines, i, end),
                      'doc': _doc_before(lines, i, crx), 'calls': calls[:40]})
    var = collections.OrderedDict()
    for i, ln in enumerate(lines, 1):
        m = re.match(r'^\s*(?:export\s+|readonly\s+|local\s+|declare\s+(?:-\w+\s+)?)?([A-Za-z_]\w*)=(.*)$', ln)
        if m and m.group(1) not in var:
            var[m.group(1)] = (i, m.group(2).strip()[:100])
    outline = []
    if lines and lines[0].startswith('#!'):
        outline.append(f'Interpreter: `{lines[0][2:].strip()}`')
    if var:
        outline.append({'heading': f'Variables ({len(var)})'})
        outline += [f'`{k}` = `{v[1]}` (l. {v[0]})' if v[1] else f'`{k}` (l. {v[0]})'
                    for k, v in list(var.items())[:300]]
    cmds = collections.Counter()
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith('#'):
            continue
        mm = _SH_CMD.match(s)
        if mm and mm.group(1) not in _SH_KW and not re.match(r'^\w+=', s):
            cmds[mm.group(1)] += 1
    meta = [('Lines', len(lines)), ('Functions', len(funcs))]
    if cmds:
        meta.append(('Commands used', ', '.join(f'`{c}`' for c, _ in cmds.most_common(20))))
    pars = [t for _, t in blocks]
    summ = _first_comment_summary(blocks)
    if not summ:
        summ = (f'{typ} of {len(lines)} lines' + (f' defining {len(funcs)} functions' if funcs else '')
                + (f'; runs ' + ', '.join(c for c, _ in cmds.most_common(8)) if cmds else '') + '.')
    return {'kind': 'source', 'type': typ, 'functions': funcs, 'outline': outline, 'paragraphs': pars,
            'meta': meta, 'summary': summ, 'code_lang': 'bash',
            'keywords': [c for c, _ in cmds.most_common(5)] + [f['name'] for f in funcs[:5]]}


_BAT_KW = {'echo', 'rem', 'set', 'if', 'goto', 'call', 'for', 'exit', 'cd', 'pause', 'shift', 'setlocal',
           'endlocal', 'cls', '@echo', 'else', 'not', 'exist', 'errorlevel', 'do', 'in'}


def _batch(path, text):
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    crx = re.compile(r'^@?(?:rem(?:\s|$)|::)\s?', re.I)
    blocks = _comment_blocks(lines, [crx])
    labels = [(i, m.group(1)) for i, ln in enumerate(lines)
              if (m := re.match(r'^\s*:(?!:)([A-Za-z_][\w.\-]*)', ln))]
    funcs = []
    for k, (i, n) in enumerate(labels):
        end = labels[k + 1][0] if k + 1 < len(labels) else len(lines)
        calls = []
        for ln in lines[i + 1:end]:
            for m in re.finditer(r'\b(?:goto|call)\s+:?([^\s&|]+)', ln, re.I):
                c = m.group(1)
                if c.lower() != ':eof' and c not in calls:
                    calls.append(c)
        funcs.append({'name': n, 'kind': 'batch label', 'line': i + 1, 'signature': _body(lines, i, end, 30),
                      'doc': _doc_before(lines, i, crx), 'calls': calls})
    var = collections.OrderedDict()
    cmds = collections.Counter()
    calls_top = []
    for i, ln in enumerate(lines, 1):
        s = ln.strip().lstrip('@')
        m = re.match(r'^set\s+(?:/[ap]\s+)?"?([A-Za-z_][\w]*)=(.*?)"?$', s, re.I)
        if m and m.group(1) not in var:
            var[m.group(1)] = (i, m.group(2)[:100])
        if not s or crx.match(ln.strip()) or s.startswith(':'):
            continue
        mm = re.match(r'^([A-Za-z0-9_.\\/:\-~%"]+)', s)
        if mm:
            c = mm.group(1).strip('"')
            if c.lower() not in _BAT_KW:
                cmds[c] += 1
        for m2 in re.finditer(r'\bcall\s+([^\s&|]+)', s, re.I):
            if m2.group(1) not in calls_top:
                calls_top.append(m2.group(1))
    outline = []
    if var:
        outline.append({'heading': f'Variables ({len(var)})'})
        outline += [f'`{k}` = `{v[1]}` (l. {v[0]})' for k, v in list(var.items())[:300]]
    meta = [('Lines', len(lines)), ('Labels', len(funcs))]
    if cmds:
        meta.append(('Programs / commands run', ', '.join(f'`{c}`' for c, _ in cmds.most_common(20))))
    if calls_top:
        meta.append(('CALL targets', ', '.join(f'`{c}`' for c in calls_top[:20])))
    pars = [t for _, t in blocks]
    # also keep echoed messages as text (often the only prose in a batch file)
    echoes = [re.sub(r'^@?echo\s?', '', ln.strip(), flags=re.I) for ln in lines
              if re.match(r'^\s*@?echo\s+(?!off\b|on\b)\S', ln, re.I)]
    if echoes:
        pars.append({'heading': 'Echoed messages'})
        pars += _split('\n'.join(echoes))
    summ = _first_comment_summary(blocks)
    if not summ:
        top = [c for c, _ in cmds.most_common(8)]
        summ = (f'Windows batch file of {len(lines)} lines'
                + (f' with {len(funcs)} labels' if funcs else '')
                + (f'; runs {", ".join(top)}' if top else '') + '.')
        if len(lines) <= 6:
            code = ' ⏎ '.join(l.strip() for l in lines if l.strip())[:300]
            if code:
                summ += f' Commands: {code}'
    return {'kind': 'source', 'type': 'Windows batch script', 'functions': funcs, 'outline': outline,
            'paragraphs': pars, 'meta': meta, 'summary': summ, 'code_lang': 'bat',
            'keywords': [os.path.basename(c.replace('\\', '/')) for c, _ in cmds.most_common(6)]}


def _make(path, text, typ='Makefile'):
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    # join continuation lines for analysis but keep the original line numbers
    logical = []
    i = 0
    while i < len(lines):
        start, buf = i, lines[i]
        while buf.endswith('\\') and i + 1 < len(lines):
            i += 1
            buf = buf[:-1] + ' ' + lines[i].strip()
        logical.append((start, buf))
        i += 1
    crx = re.compile(r'^#+\s?')
    blocks = _comment_blocks(lines, [crx])
    var = collections.OrderedDict()
    funcs, includes = [], []
    tre = re.compile(r'^([^\t#=:][^#=:]*?)\s*(::?)(?!=)\s*(.*)$')
    for k, (ln_no, ln) in enumerate(logical):
        if ln.startswith('\t') or not ln.strip() or ln.lstrip().startswith('#'):
            continue
        m = re.match(r'^\s*(?:export\s+|override\s+)?([A-Za-z_.][\w.\-]*)\s*([:+?!]?=)\s*(.*)$', ln)
        if m:
            if m.group(1) not in var:
                var[m.group(1)] = (ln_no + 1, m.group(2), m.group(3).strip()[:120])
            continue
        m = re.match(r'^\s*-?(?:include|sinclude)\s+(.*)$', ln)
        if m:
            includes.append(m.group(1).strip())
            continue
        if re.match(r'^\s*(ifeq|ifneq|ifdef|ifndef|else|endif|define|endef|vpath)\b', ln):
            continue
        m = tre.match(ln)
        if m and m.group(1).strip():
            targets = m.group(1).split()
            rest = m.group(3)
            prereq, recipe_inline = (rest.split(';', 1) + [''])[:2]
            prereqs = [p for p in prereq.split() if p != '|']
            # recipe = following tab lines
            body_end = k + 1
            while body_end < len(logical) and (logical[body_end][1].startswith('\t') or
                                               (not logical[body_end][1].strip() and body_end + 1 < len(logical)
                                                and logical[body_end + 1][1].startswith('\t'))):
                body_end += 1
            recipe = [logical[j][1].strip() for j in range(k + 1, body_end) if logical[j][1].strip()]
            if recipe_inline.strip():
                recipe.insert(0, recipe_inline.strip())
            end_line = logical[body_end][0] if body_end < len(logical) else len(lines)
            cmds = []
            for rl in recipe:
                rl = rl.lstrip('@-+ ')
                mm = re.match(r'^(\$\([A-Za-z_]\w*\)|[\w./\-]+)', rl)
                if mm and mm.group(1) not in cmds:
                    cmds.append(mm.group(1))
            special = targets[0].startswith('.') and targets[0].isupper()
            doc = _doc_before(lines, ln_no, crx)
            for t in targets[:1] if len(targets) > 6 else targets:
                funcs.append({'name': t if len(targets) <= 6 else ' '.join(targets[:6]) + ' …',
                              'kind': 'special target' if special else ('pattern rule' if '%' in t else 'make target'),
                              'line': ln_no + 1, 'signature': _body(lines, ln_no, end_line, 40),
                              'doc': doc or ('' if recipe else 'Dependency-only rule (no recipe).'),
                              'params': [(p, 'prerequisite', '') for p in prereqs[:60]],
                              'calls': prereqs[:30] + [c for c in cmds if c not in prereqs]})
    outline = []
    if includes:
        outline.append({'heading': 'Includes'})
        outline += [f'`{x}`' for x in includes]
    if var:
        outline.append({'heading': f'Variables ({len(var)})'})
        outline += [f'`{k} {v[1]} {v[2]}` (l. {v[0]})' for k, v in list(var.items())[:300]]
    real = [f['name'] for f in funcs if f['kind'] == 'make target']
    meta = [('Lines', len(lines)), ('Rules', len(funcs)), ('Variables', len(var))]
    for key in ('CC', 'CXX', 'AS', 'LD', 'MCU', 'TARGET', 'PROJECT', 'DEVICE', 'CPU', 'ARCH'):
        if key in var:
            meta.append((key, var[key][2]))
    pars = [t for _, t in blocks]
    summ = _first_comment_summary(blocks)
    lead = (f'{typ} with {_pl(len(funcs), "rule")}' + (f' ({", ".join(real[:10])}' + (' …' if len(real) > 10 else '') + ')' if real else '')
            + f' and {_pl(len(var), "variable")}' + (f'; default target {real[0]}' if real else '') + '.')
    summ = (summ + ' — ' + lead) if summ else lead
    return {'kind': 'source', 'type': typ, 'functions': funcs, 'outline': outline, 'paragraphs': pars,
            'meta': meta, 'summary': summ, 'code_lang': 'makefile',
            'keywords': [v[2] for k, v in var.items() if k in ('TARGET', 'PROJECT', 'MCU', 'DEVICE')] + real[:6]}


def _perl(path, text):
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    crx = re.compile(r'^(?!#!)#+\s?')
    blocks = _comment_blocks(lines, [crx])
    pod, inpod, cur = [], False, []
    for ln in lines:
        if re.match(r'^=(head\d|pod|item|over|back|begin|for|encoding)', ln):
            inpod = True
        if inpod:
            if ln.startswith('=cut'):
                inpod = False
                continue
            cur.append(re.sub(r'^=(head\d|item|pod|over|back)\s*', '', ln))
    if cur:
        pod = _split('\n'.join(cur))
    subs = [(i, m.group(1)) for i, ln in enumerate(lines) if (m := re.match(r'^\s*sub\s+([\w:]+)', ln))]
    names = {n for _, n in subs}
    funcs = []
    for k, (i, n) in enumerate(subs):
        end = subs[k + 1][0] if k + 1 < len(subs) else len(lines)
        for j in range(i + 1, end):
            if re.match(r'^\}\s*$', lines[j]):
                end = j + 1
                break
        body = '\n'.join(lines[i + 1:end])
        calls = []
        for m in re.finditer(r'(?:&|\b)([A-Za-z_]\w*)\s*\(', body):
            c = m.group(1)
            if c not in calls and c not in ('if', 'elsif', 'while', 'for', 'foreach', 'unless', 'my', 'return',
                                            'print', 'qw', 'and', 'or', 'not'):
                calls.append(c)
        calls.sort(key=lambda c: c not in names)
        params = re.findall(r'my\s*\(([^)]*)\)\s*=\s*@_', body[:600])
        funcs.append({'name': n, 'kind': 'sub', 'line': i + 1, 'signature': _body(lines, i, end, 30),
                      'doc': _doc_before(lines, i, crx),
                      'params': [(p.strip(), '', '') for p in params[0].split(',')] if params else [],
                      'calls': calls[:40]})
    uses = [m.group(1) for ln in lines if (m := re.match(r'^\s*(?:use|require)\s+([\w:]+)', ln))]
    outline = ([{'heading': 'Modules used'}] + [f'`{u}`' for u in dict.fromkeys(uses)]) if uses else []
    pars = [t for _, t in blocks] + ([{'heading': 'POD documentation'}] + pod if pod else [])
    summ = _first_comment_summary(blocks) or (pod[0][:500] if pod else '')
    return {'kind': 'source', 'type': 'Perl script', 'functions': funcs, 'outline': outline, 'paragraphs': pars,
            'meta': [('Lines', len(lines)), ('Subs', len(funcs))], 'summary': summ, 'code_lang': 'perl'}


def _awk(path, text):
    lines = text.replace('\r\n', '\n').split('\n')
    crx = re.compile(r'^(?!#!)#+\s?')
    blocks = _comment_blocks(lines, [crx])
    funcs = []
    for i, ln in enumerate(lines):
        m = re.match(r'^\s*func(?:tion)?\s+(\w+)\s*\(([^)]*)\)', ln)
        if m:
            funcs.append({'name': m.group(1), 'kind': 'awk function', 'line': i + 1, 'signature': ln.strip(),
                          'doc': _doc_before(lines, i, crx),
                          'params': [(p.strip(), '', '') for p in m.group(2).split(',') if p.strip()]})
        elif re.match(r'^\s*(BEGIN|END)\b', ln):
            funcs.append({'name': ln.split()[0], 'kind': 'awk block', 'line': i + 1, 'signature': ln.strip(),
                          'doc': _doc_before(lines, i, crx)})
    return {'kind': 'source', 'type': 'AWK script', 'functions': funcs, 'paragraphs': [t for _, t in blocks],
            'summary': _first_comment_summary(blocks), 'code_lang': 'awk', 'meta': [('Lines', len(lines))]}


def _sed(path, text):
    lines = text.replace('\r\n', '\n').split('\n')
    crx = re.compile(r'^(?!#!)#+\s?')
    blocks = _comment_blocks(lines, [crx])
    funcs = [{'name': m.group(1), 'kind': 'sed label', 'line': i + 1, 'signature': ln.strip(),
              'doc': _doc_before(lines, i, crx)}
             for i, ln in enumerate(lines) if (m := re.match(r'^\s*:\s*(\S+)', ln))]
    cmds = [l.strip() for l in lines if l.strip() and not l.strip().startswith('#')]
    return {'kind': 'source', 'type': 'sed script', 'functions': funcs,
            'paragraphs': [t for _, t in blocks] + ([{'heading': 'Commands'}, '\n'.join(cmds[:500])] if cmds else []),
            'summary': _first_comment_summary(blocks) or f'sed script with {len(cmds)} commands.',
            'code_lang': 'sed', 'meta': [('Lines', len(lines))]}


def _coregen_in(text):
    kv = collections.OrderedDict()
    params = []
    for ln in text.splitlines():
        m = re.match(r'^(SET_PREFERENCE|SET_CORE_NAME|SET_CORE_VERSION|SET_CORE_VLNV|SET_PARAMETER)\s+(\S+)?\s*(.*)$', ln.strip())
        if not m:
            continue
        if m.group(1) == 'SET_PREFERENCE':
            kv.setdefault(m.group(2), m.group(3))
        elif m.group(1) == 'SET_PARAMETER':
            params.append(f'`{m.group(2)}` = `{m.group(3)}`')
        else:
            kv.setdefault(m.group(1), ((m.group(2) or '') + ' ' + m.group(3)).strip())
    core_ = kv.get('SET_CORE_NAME', '?')
    comp = next((p.split('`')[3] for p in params if p.startswith('`Component_Name`')), '')
    dev = ' '.join(x for x in (kv.get('device', ''), kv.get('speedgrade', ''), kv.get('package', '')) if x)
    meta = [(k, v) for k, v in (('Core', core_), ('Core version', kv.get('SET_CORE_VERSION', '')),
                                ('VLNV', kv.get('SET_CORE_VLNV', '')), ('Component name', comp),
                                ('Device family', kv.get('devicefamily', '')), ('Device', dev)) if v]
    outline = [{'heading': 'Preferences'}] + [f'`{k}` = `{v}`' for k, v in kv.items() if not k.startswith('SET_')]
    if params:
        outline += [{'heading': f'Core parameters ({len(params)})'}] + params[:400]
    return {'kind': 'data', 'type': 'Xilinx CORE Generator command input', 'meta': meta, 'outline': outline,
            'summary': f'Xilinx CORE Generator batch input that (re)generates the {core_} '
                       f'{kv.get("SET_CORE_VERSION", "")} core{" " + comp if comp else ""}'
                       f'{" for " + dev if dev else ""} (tool-generated temporary file).',
            'keywords': [x for x in (comp, core_, kv.get('device', '')) if x]}


def _plain(path, text, typ='Text document', trunc=False):
    pars = _split(text)
    r = {'kind': 'document', 'type': typ, 'paragraphs': pars}
    if trunc:
        r['notes'] = ['File larger than 20 MB: text truncated.']
    return r


# ======================================================================== no extension: sniff
_ELF_MACH = {2: 'SPARC', 3: 'Intel 80386', 8: 'MIPS', 20: 'PowerPC', 40: 'ARM', 42: 'SuperH', 50: 'IA-64',
             62: 'x86-64', 83: 'AVR', 105: 'TI MSP430', 106: 'Blackfin', 183: 'AArch64', 243: 'RISC-V',
             92: 'OpenRISC', 189: 'Xilinx MicroBlaze', 0xbaab: 'Xilinx MicroBlaze (old)', 164: 'Qualcomm Hexagon',
             94: 'Tensilica Xtensa', 75: 'Digital VAX', 4: 'Motorola 68000', 0x1057: 'Altera Nios II', 113: 'Altera Nios II'}
_PE_MACH = {0x14c: 'Intel 386', 0x8664: 'x86-64', 0x1c0: 'ARM', 0x1c2: 'ARM Thumb', 0x1c4: 'ARMv7',
            0xaa64: 'ARM64', 0x200: 'IA-64', 0x166: 'MIPS'}


def _elf(path, data):
    cls = {1: '32-bit', 2: '64-bit'}.get(data[4], '?')
    end = '<' if data[5] == 1 else '>'
    et, em = struct.unpack(end + 'HH', data[16:20])
    typ = {1: 'relocatable object', 2: 'executable', 3: 'shared object', 4: 'core dump'}.get(et, f'type {et}')
    mach = _ELF_MACH.get(em, f'machine {em}')
    meta = [('Format', f'ELF {cls} {"little" if end == "<" else "big"}-endian {typ}'), ('Architecture', mach)]
    secs = []
    try:
        if data[4] == 1:
            shoff = struct.unpack(end + 'I', data[32:36])[0]
            shentsize, shnum, shstrndx = struct.unpack(end + 'HHH', data[46:52])
        else:
            shoff = struct.unpack(end + 'Q', data[40:48])[0]
            shentsize, shnum, shstrndx = struct.unpack(end + 'HHH', data[58:64])
        with open(path, 'rb') as f:
            f.seek(shoff)
            sh = f.read(shentsize * shnum)
            def ent(k):
                e = sh[k * shentsize:(k + 1) * shentsize]
                if data[4] == 1:
                    nm, _t, _fl, _a, off, size = struct.unpack(end + 'IIIIII', e[:24])
                else:
                    nm, _t = struct.unpack(end + 'II', e[:8]); off, size = struct.unpack(end + 'QQ', e[24:40])
                return nm, off, size
            _, so, ss = ent(shstrndx)
            f.seek(so)
            strtab = f.read(ss)
            for k in range(min(shnum, 200)):
                nm, off, size = ent(k)
                n = strtab[nm:strtab.find(b'\x00', nm)].decode('latin-1')
                if n:
                    secs.append(f'`{n}` · {size:,}')
    except Exception:
        pass
    if secs:
        meta.append(('Sections', len(secs)))
    with open(path, 'rb') as f:
        blob = f.read(8 * 1024 * 1024)
    strs = _strings(blob, 6, 1500)
    return {'kind': 'binary', 'type': f'ELF {typ} ({mach})', 'meta': meta,
            'outline': ([{'heading': 'Sections: name · size in bytes'}] + secs) if secs else [],
            'paragraphs': ([{'heading': 'Printable strings'}] + _strings_pars(strs)) if strs else [],
            'summary': f'Compiled ELF {cls} {typ} for {mach} (no file extension).',
            'notes': ['Binary executable: printable strings shown, code not disassembled.']}


def _pe(path, data):
    meta, typ = [], 'MS-DOS executable'
    try:
        off = struct.unpack('<I', data[0x3c:0x40])[0]
        if data[off:off + 4] == b'PE\x00\x00':
            mach, nsec, ts = struct.unpack('<HHI', data[off + 4:off + 12])
            ch = struct.unpack('<H', data[off + 22:off + 24])[0]
            magic = struct.unpack('<H', data[off + 24:off + 26])[0]
            sub = struct.unpack('<H', data[off + 24 + 68:off + 24 + 70])[0]
            subs = {1: 'native', 2: 'Windows GUI', 3: 'Windows console', 9: 'Windows CE GUI', 10: 'EFI'}
            typ = ('Windows DLL' if ch & 0x2000 else 'Windows executable') + (' (PE32+)' if magic == 0x20b else ' (PE32)')
            meta += [('Machine', _PE_MACH.get(mach, hex(mach))), ('Subsystem', subs.get(sub, sub)),
                     ('Sections', nsec), ('Link timestamp', _ts(ts))]
        elif data[off:off + 2] in (b'NE', b'LE', b'LX'):
            typ = f'{data[off:off + 2].decode()} (16-bit Windows/OS2) executable'
    except Exception:
        pass
    with open(path, 'rb') as f:
        blob = f.read(8 * 1024 * 1024)
    strs = _strings(blob, 6, 1500)
    return {'kind': 'binary', 'type': typ, 'meta': meta,
            'paragraphs': ([{'heading': 'Printable strings'}] + _strings_pars(strs)) if strs else [],
            'summary': f'{typ} (no file extension).',
            'notes': ['Binary executable: printable strings shown, code not disassembled.']}


def _ihex(text):
    recs = n = 0
    base, lo, hi, start = 0, None, None, None
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln.startswith(':') or len(ln) < 11:
            continue
        try:
            cnt, addr, rt = int(ln[1:3], 16), int(ln[3:7], 16), int(ln[7:9], 16)
        except ValueError:
            continue
        recs += 1
        if rt == 0:
            a = base + addr
            lo = a if lo is None else min(lo, a)
            hi = a + cnt if hi is None else max(hi, a + cnt)
            n += cnt
        elif rt == 2:
            base = int(ln[9:13], 16) << 4
        elif rt == 4:
            base = int(ln[9:13], 16) << 16
        elif rt in (3, 5):
            start = ln[9:9 + cnt * 2]
    meta = [('Records', f'{recs:,}'), ('Data bytes', f'{n:,}')]
    if lo is not None:
        meta.append(('Address range', f'0x{lo:08X} – 0x{hi - 1:08X}'))
    if start:
        meta.append(('Start address', '0x' + start))
    return {'kind': 'data', 'type': 'Intel HEX firmware image', 'meta': meta,
            'summary': f'Intel HEX firmware image: {n:,} data bytes in {recs:,} records'
                       + (f', address 0x{lo:X}–0x{hi - 1:X}' if lo is not None else '') + '.',
            'notes': ['Machine code in hex records; not disassembled.']}


def _srec(text):
    recs = n = 0
    lo = hi = None
    hdr = ''
    for ln in text.splitlines():
        ln = ln.strip()
        if len(ln) < 4 or ln[0] != 'S' or not ln[1].isdigit():
            continue
        t = ln[1]
        try:
            cnt = int(ln[2:4], 16)
        except ValueError:
            continue
        recs += 1
        al = {'1': 2, '2': 3, '3': 4}.get(t)
        if t == '0':
            try:
                hdr = bytes.fromhex(ln[8:4 + cnt * 2 - 2]).decode('latin-1').strip('\x00 ')
            except Exception:
                pass
        if al:
            a = int(ln[4:4 + al * 2], 16)
            dn = cnt - al - 1
            n += dn
            lo = a if lo is None else min(lo, a)
            hi = a + dn if hi is None else max(hi, a + dn)
    meta = [('Records', f'{recs:,}'), ('Data bytes', f'{n:,}')]
    if hdr:
        meta.append(('Header', hdr))
    if lo is not None:
        meta.append(('Address range', f'0x{lo:08X} – 0x{hi - 1:08X}'))
    return {'kind': 'data', 'type': 'Motorola S-record firmware image', 'meta': meta,
            'summary': f'Motorola S-record image{" " + hdr if hdr else ""}: {n:,} data bytes.'}


def _sniff_text_lang(name, text):
    head = text[:6000]
    hl = head.lower()
    first = head.lstrip('﻿').split('\n', 1)[0]
    if first.startswith('#!'):
        if 'perl' in first: return 'pl'
        if 'python' in first: return 'py'
        if re.search(r'\b(tclsh|wish)\b', first): return 'tcl'
        if 'awk' in first: return 'awk'
        if re.search(r'\b(sh|bash|ksh|zsh|dash|csh|tcsh)\b', first): return 'sh'
    if 'makefile' in name or name in ('gnumakefile',):
        return 'make'
    if re.search(r'<!doctype html|<html\b', hl):
        return 'html'
    if hl.lstrip().startswith('<?xml'):
        return 'xml'
    if re.search(r'^\s*(library\s+ieee|entity\s+\w+\s+is\b)', hl, re.M):
        return 'vhd'
    if re.search(r'^\s*module\s+\w+\s*[#(;]', head, re.M) and 'endmodule' in text:
        return 'v'
    c = len(re.findall(r'^\s*#\s*(include|define|ifn?def|endif|pragma)\b', head, re.M))
    c += len(re.findall(r'^\s*(?:static\s+|extern\s+)?(?:void|int|char|unsigned|long|float|double|struct|typedef)\b', head, re.M))
    cpp = re.search(r'\b(template\s*<|namespace\s+\w+|class\s+\w+\s*[:{]|public:|private:|std::)', head)
    if c >= 3 or (c >= 1 and ('/*' in head or '{' in head)):
        return 'cpp' if cpp else 'c'
    if cpp and '{' in head:
        return 'cpp'
    tabs = len(re.findall(r'^[\w.$()%/\-]+\s*:[^=].*\n\t', head, re.M))
    if tabs >= 2 and re.search(r'^\w+\s*[:?+]?=', head, re.M):
        return 'make'
    if re.search(r'^\s*(use strict;|use warnings;|sub \w+\s*\{)', head, re.M):
        return 'pl'
    if re.search(r'^@?echo off', hl, re.M) or re.search(r'^\s*rem\s', hl, re.M):
        return 'bat'
    return ''


def _noext(path, name):
    size = os.path.getsize(path)
    if size == 0:
        return {'kind': 'binary', 'type': 'Empty file', 'summary': 'Empty file (0 bytes).', 'notes': ['File is empty.']}
    with open(path, 'rb') as f:
        head = f.read(8192)
    # --- binary magics
    if head[:4] == b'\x7fELF':
        return _elf(path, head)
    if head[:2] == b'MZ':
        return _pe(path, head)
    if head[:4] == b'PK\x03\x04' or head[:4] == b'PK\x05\x06':
        return _zip(path)
    if head[:5] == b'%PDF-':
        return _delegate(path, 'pdf') or {'kind': 'binary', 'type': 'PDF document (no extension)',
                                          'summary': 'PDF document without a file extension.'}
    if head[:8] == bytes.fromhex('d0cf11e0a1b11ae1'):
        for e in ('doc', 'xls', 'msg', 'ppt'):
            r = _delegate(path, e)
            if r and r.get('paragraphs'):
                return r
        strs = _strings(open(path, 'rb').read(8 * 1024 * 1024), 6, 1500)
        return {'kind': 'binary', 'type': 'OLE2 compound document (Office/Altium)',
                'summary': 'Microsoft OLE2 compound file (Office, Altium or similar) without an extension.',
                'paragraphs': _strings_pars(strs), 'notes': ['Printable strings only; structure not decoded.']}
    if head[:4] == b'\xca\xfe\xba\xbe' and struct.unpack('>H', head[6:8])[0] >= 45:
        return _class(path)
    if head[:4] == b'Rar!':
        return _rar(path)
    if head[:6] == b"7z\xbc\xaf'\x1c":
        return _7z(path)
    if head[:2] == b'\x1f\x8b':
        return _gz(path, 'gz')
    if head[257:262] == b'ustar':
        return _tar(path)
    if head[:4] == b'RIFF':
        return _riff(path) or _bin_generic(path, head)
    if head[:3] == b'ID3':
        return _mp3(path)
    if head[4:8] in (b'ftyp', b'moov', b'mdat'):
        return _mp4(path)
    for sig, ext in ((b'\x89PNG', 'png'), (b'\xff\xd8\xff', 'jpg'), (b'GIF8', 'gif'), (b'BM', 'bmp'),
                     (b'II*\x00', 'tif'), (b'MM\x00*', 'tif'), (b'\x0a\x05\x01', 'pcx')):
        if head.startswith(sig):
            r = _image(path, ext)
            if r and 'unreadable' not in r.get('type', ''):
                return r
    if head[:4] == b'TZif':
        return {'kind': 'data', 'type': 'Time-zone database file (TZif)',
                'summary': f'Compiled time-zone rules (TZif v{head[4:5].decode("latin-1") or "1"}) for {name}, '
                           'part of a bundled Java/OS zoneinfo tree.'}
    if head[:6] in (b'javazi', b'javazm'):
        return {'kind': 'data', 'type': 'Java time-zone data (JRE lib/zi)',
                'summary': f'Compiled Java Runtime time-zone rules for {os.path.basename(path)} '
                           '(part of a bundled JRE lib/zi tree; not WBS-authored).'}
    if head[:4] in (b'AC10', b'AC1.', b'AC2.', b'AC1\x00'):
        dwg = {'AC1009': 'R11/R12', 'AC1012': 'R13', 'AC1014': 'R14', 'AC1015': '2000', 'AC1018': '2004',
               'AC1021': '2007', 'AC1024': '2010', 'AC1027': '2013', 'AC1006': 'R10', 'AC1004': 'R9',
               'AC1003': '2.6', 'AC1002': '2.5'}
        v = head[:6].decode('latin-1')
        r = _delegate(path, 'dwg')
        if r:
            return r
        return {'kind': 'binary', 'type': f'AutoCAD drawing (DWG {dwg.get(v, v)})',
                'summary': f'AutoCAD DWG drawing, format {v} (AutoCAD {dwg.get(v, "?")}), without a file extension.',
                'meta': [('DWG version', f'{v} — AutoCAD {dwg.get(v, "?")}')]}
    lp = path.replace('\\', '/')
    if '/_temp/vlog' in lp or re.search(r'/wlf[a-z0-9]{6,}$', lp):
        return {'kind': 'binary', 'type': 'ModelSim/Questa temporary file',
                'summary': 'ModelSim/Questa simulator temporary work file (compiler scratch or waveform log '
                           'fragment); tool-generated, no human-readable content.'}
    if '/__OBJSTORE__/' in lp:
        r = _bin_generic(path, head)
        r['type'] = 'Xilinx ISE object-store data'
        r['summary'] = 'Xilinx ISE project object-store file (tool-generated database fragment). ' + r['summary']
        return r
    if head[:4] == b'\xfe\xed\xfe\xed':
        return {'kind': 'binary', 'type': 'Java KeyStore (JKS)', 'summary': 'Java KeyStore (certificate/key store).',
                'notes': ['Key material not read.']}
    if head[:3] == b'BZh':
        return {'kind': 'data', 'type': 'bzip2 compressed file', 'summary': f'bzip2-compressed data, {_size(size)}.'}
    if _is_binary_bytes(head):
        return _bin_generic(path, head)
    # --- text
    text, trunc = _read_text(path)
    t0 = text.lstrip()[:200]
    if re.match(r'^:[0-9A-Fa-f]{10,}', t0):
        return _ihex(text)
    if re.match(r'^S[0-9][0-9A-Fa-f]{6,}', t0):
        return _srec(text)
    lang = _sniff_text_lang(name, text)
    if lang == 'sh':
        return _shell(path, text)
    if lang == 'make':
        return _make(path, text)
    if lang == 'pl':
        return _perl(path, text)
    if lang == 'bat':
        return _batch(path, text)
    if lang == 'awk':
        return _awk(path, text)
    if lang:
        r = _delegate(path, lang) or (_delegate(path, 'h') if lang == 'cpp' else None) or \
            (_delegate(path, 'cpp') if lang == 'c' else None)
        if r:
            return r
        names = {'c': 'C source (no extension)', 'cpp': 'C++ source/header (no extension)', 'html': 'HTML page',
                 'xml': 'XML document', 'vhd': 'VHDL source', 'v': 'Verilog source', 'py': 'Python script',
                 'tcl': 'Tcl script'}
        r = _plain(path, text, names.get(lang, 'Text'), trunc)
        r['kind'] = 'source' if lang not in ('html', 'xml') else 'document'
        r['notes'] = (r.get('notes') or []) + [f'No extension: content sniffed as `.{lang}`; no dedicated extractor '
                                               'available, so text is shown paragraph by paragraph.']
        return r
    typ = {'readme': 'Read-me text', 'license': 'Licence text', 'copying': 'Licence text (COPYING)',
           'changelog': 'Change log', 'todo': 'To-do list', 'install': 'Installation notes',
           'news': 'Release news'}.get(name, 'Plain text (no extension)')
    return _plain(path, text, typ, trunc)


def _bin_generic(path, head):
    with open(path, 'rb') as f:
        blob = f.read(4 * 1024 * 1024)
    strs = _strings(blob, 6, 1500)
    r = {'kind': 'binary', 'type': 'Binary data (unknown format)',
         'meta': [('First bytes', '`' + head[:16].hex(' ') + '`')],
         'summary': f'Unidentified binary data, {_size(os.path.getsize(path))}'
                    + (f'; {len(strs)} printable strings, e.g. “{strs[0][:80]}”.' if strs else '; no readable text.'),
         'notes': ['Format not recognised from magic bytes.']}
    if strs:
        r['paragraphs'] = [{'heading': 'Printable strings'}] + _strings_pars(strs)
        r['notes'].append('Printable strings (6+ characters) extracted from the first 4 MB.')
    return r


# ======================================================================== dispatch
def _script_by_ext(path, ext, name):
    data_head = open(path, 'rb').read(8192)
    if _is_binary_bytes(data_head):
        return _bin_generic(path, data_head)
    text, trunc = _read_text(path)
    if ext in ('sh', 'bash'):
        return _shell(path, text, 'Bash script' if ext == 'bash' else 'Shell script')
    if ext in ('bat', 'cmd'):
        if ext == 'cmd' and not re.search(r'(?im)^\s*@?(echo|rem|set|call|goto|if|cd|copy|del|xcopy|start)\b', text):
            # Xilinx/other tools also use .cmd for command files
            r = _plain(path, text, 'Command file')
            r['kind'] = 'source'
            return r
        return _batch(path, text)
    if ext in ('mak', 'mk', 'make', 'makefile') or name in ('makefile', 'gnumakefile'):
        return _make(path, text)
    if ext == 'am':
        return _make(path, text, 'Automake input (Makefile.am)')
    if ext == 'in':
        stem = name[:-3]
        if stem.startswith('makefile'):
            return _make(path, text, 'Makefile template (.in)')
        if stem.startswith('configure'):
            return _shell(path, text, 'Autoconf input (configure.in)')
        if 'SET_PREFERENCE' in text[:4000] or 'SET_CORE_NAME' in text:
            return _coregen_in(text)
        inner = stem.rsplit('.', 1)[1] if '.' in stem else ''
        if inner:
            r = _delegate(path, inner, ' (.in template)')
            if r:
                return r
        return _plain(path, text, 'Template input file (.in)', trunc)
    if ext == 'pl':
        # .pl is also Prolog / PLD; Perl is by far most common here
        return _perl(path, text)
    if ext == 'awk':
        return _awk(path, text)
    if ext == 'sed':
        return _sed(path, text)
    if name == 'configure':
        return _shell(path, text, 'Autoconf configure script')
    return None


def extract(path):
    try:
        return _extract(path)
    except Exception as e:
        # never raise: degrade to a minimal description
        try:
            with open(path, 'rb') as f:
                head = f.read(16)
        except Exception:
            head = b''
        return {'kind': 'binary', 'notes': [f'misc extractor error: {type(e).__name__}: {str(e)[:120]}'],
                'meta': [('First bytes', '`' + head.hex(' ') + '`')]}


def _extract(path):
    name = os.path.basename(path).lower()
    ext = name.rsplit('.', 1)[1] if '.' in name else ''
    if ext in ('zip', 'jar', 'war'):
        with open(path, 'rb') as f:
            mg = f.read(4)
        if mg[:2] != b'PK':
            if not mg:
                return {'kind': 'binary', 'type': 'Empty file', 'summary': 'Empty (0-byte) archive file.'}
            return _sniff_bad_archive(path, 'ZIP (no PK signature)')
        return _zip(path, ext)
    if ext == 'rar':
        return _rar(path)
    if ext == '7z':
        return _7z(path)
    if ext in ('gz', 'tgz'):
        return _gz(path, ext)
    if ext == 'tar':
        return _tar(path)
    if ext == 'class':
        return _class(path)
    if ext in ('png', 'jpg', 'jpeg', 'gif', 'bmp', 'tif', 'tiff', 'pcx', 'ico', 'wmf', 'emf', 'svg', 'wpg'):
        return _image(path, ext)
    if ext == 'wav':
        return _wav(path)
    if ext == 'avi':
        return _riff(path) or _bin_generic(path, open(path, 'rb').read(16))
    if ext in ('m4a', 'mp4', 'mov'):
        return _mp4(path)
    if ext == 'mp3':
        return _mp3(path)
    if ext == 'wma':
        return _wma(path)
    if name in NAMES and name not in ('makefile', 'gnumakefile', 'configure'):
        return _noext(path, name)
    r = _script_by_ext(path, ext, name) if (ext or name in ('makefile', 'gnumakefile', 'configure')) else None
    if r is not None:
        return r
    return _noext(path, name)
