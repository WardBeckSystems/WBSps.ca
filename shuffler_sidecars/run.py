#!/usr/bin/env python3
"""Write a <file>.md sidecar next to every file in WBS - DATA SHUFFLER.

  python3 run.py hash                       # pass 1: SHA-256 of every file -> hashes.tsv
  python3 run.py write                      # pass 2: write every sidecar into the archive
  python3 run.py test --ext v,vhd --limit 30 [--out DIR]
        # write sidecars for a sample into DIR (default preview/) mirroring the tree,
        # never touching the archive. Prints which extractor handled each file.

Extractors live in extractors/*.py (see core.py for the contract).
"""
import os, sys, time, signal, hashlib, importlib, argparse, traceback, urllib.parse, datetime
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import core

ROOT = os.path.join(os.path.dirname(HERE), 'WBS - DATA SHUFFLER')
HASHES = os.path.join(HERE, 'hashes.tsv')
AUDIT = 'WBS - DATA SHUFFLER - AUDIT.md'
TIMEOUT = 120
MAX_TEXT_CHARS = 3_000_000   # cap on full text written per sidecar

# ---------------------------------------------------------------- extractors
REG_EXT, REG_NAME, LOAD_ERR = {}, {}, []


def load_extractors():
    d = os.path.join(HERE, 'extractors')
    for fn in sorted(os.listdir(d)):
        if not fn.endswith('.py') or fn.startswith('_'):
            continue
        name = fn[:-3]
        try:
            m = importlib.import_module('extractors.' + name)
        except Exception as e:
            LOAD_ERR.append(f'{name}: {e!r}')
            continue
        for e in getattr(m, 'EXTS', ()):
            REG_EXT.setdefault(e.lower(), m)
        for n in getattr(m, 'NAMES', ()):
            REG_NAME.setdefault(n.lower(), m)


def generic(path):
    if core.looks_binary(path):
        with open(path, 'rb') as f:
            head = f.read(16)
        return {'kind': 'binary', 'notes': ['Binary file: no text to extract.'],
                'meta': [('First bytes', '`' + head.hex(' ') + '`')]}
    text, trunc = core.read_text(path)
    r = {'kind': 'document', 'paragraphs': core.split_paragraphs(text)}
    if trunc:
        r['notes'] = ['File larger than 20 MB: text truncated.']
    return r


class Timeout(Exception):
    pass


def _alarm(*_):
    raise Timeout()


def run_extractor(path):
    name = os.path.basename(path).lower()
    ext = name.rsplit('.', 1)[1] if '.' in name else ''
    mod = REG_NAME.get(name) or REG_EXT.get(ext)
    used = mod.__name__.split('.')[-1] if mod else 'generic'
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(TIMEOUT)
    try:
        r = (mod.extract(path) if mod else generic(path)) or {}
    except Timeout:
        r = generic(path); r.setdefault('notes', []).append(f'{used} extractor timed out; generic fallback used.')
        used += '(timeout)'
    except Exception as e:
        try:
            r = generic(path)
        except Exception:
            r = {'kind': 'binary'}
        r.setdefault('notes', []).append(f'{used} extractor failed ({type(e).__name__}: {str(e)[:120]}); generic fallback used.')
        used += '(error)'
    finally:
        signal.alarm(0)
    return r, used

# ---------------------------------------------------------------- hashing
def _hash(p):
    h = hashlib.sha256()
    try:
        with open(p, 'rb') as f:
            for b in iter(lambda: f.read(1 << 20), b''):
                h.update(b)
        return p, h.hexdigest(), os.path.getsize(p)
    except Exception:
        return p, '', 0


def all_files():
    for dp, dn, fn in os.walk(ROOT):
        dn.sort()
        for f in sorted(fn):
            if f.lower().endswith('.md'):
                continue
            p = os.path.join(dp, f)
            if os.path.islink(p) or not os.path.isfile(p):
                continue
            yield p


def cmd_hash():
    files = list(all_files())
    t = time.time()
    with Pool(os.cpu_count()) as pool, open(HASHES + '.tmp', 'w') as out:
        for i, (p, h, s) in enumerate(pool.imap_unordered(_hash, files, chunksize=64)):
            out.write(f'{h}\t{s}\t{os.path.relpath(p, ROOT)}\n')
            if i % 20000 == 0:
                print(f'{i}/{len(files)} {time.time()-t:.0f}s', flush=True)
    os.replace(HASHES + '.tmp', HASHES)
    print('hashed', len(files))


SHA, DUPS = {}, {}


def load_hashes():
    if not os.path.exists(HASHES):
        return
    by = {}
    with open(HASHES) as f:
        for line in f:
            h, s, rel = line.rstrip('\n').split('\t', 2)
            SHA[rel] = h
            if h:
                by.setdefault(h, []).append(rel)
    for h, rels in by.items():
        if len(rels) > 1:
            DUPS[h] = rels

# ---------------------------------------------------------------- rendering
def wy(y):
    return f'{y}|{y - 1967}'


def link(from_rel_dir, target_rel, text=None):
    rel = os.path.relpath(target_rel, from_rel_dir or '.')
    return f'[{text or target_rel}]({urllib.parse.quote(rel)})'


def esc_par(p):
    p = p.replace('\r', '')
    # keep text literal: neutralise markdown block starters at line starts
    lines = []
    for ln in p.split('\n'):
        s = ln.lstrip()
        if s[:1] in '#>|=' or s[:2] in ('- ', '* ', '+ ') or s.startswith('```') or s.startswith('~~~'):
            ln = '\\' + s
        lines.append(ln.rstrip())
    return '  \n'.join(lines)


def fence(code, lang=''):
    f = '```'
    while f in code:
        f += '`'
    return f'{f}{lang}\n{code}\n{f}'


def render(path, r, used):
    rel = os.path.relpath(path, ROOT)
    rel_dir = os.path.dirname(rel)
    name = os.path.basename(path)
    st = os.stat(path)
    mt = datetime.datetime.fromtimestamp(st.st_mtime)
    top = rel.split(os.sep)[0] if os.sep in rel else '(archive root)'
    ext = name.rsplit('.', 1)[1].lower() if '.' in name else ''
    kind = r.get('kind') or 'document'
    pars = r.get('paragraphs') or []
    funcs = r.get('functions') or []
    outline = r.get('outline') or []
    L = [f'# {name}', '']
    L.append(f'Product folder: **{top}** · Folder: `{rel_dir or "."}`  ')
    L.append(f'Archive: WBS - DATA SHUFFLER · Audit: {link(rel_dir, AUDIT, "archive audit")}')
    L.append('')

    # summary + keywords
    summ = r.get('summary') or ''
    if not summ and kind == 'source' and funcs:
        names = [f.get('name', '?') for f in funcs]
        summ = (f"{r.get('type') or 'Source file'} defining {len(funcs)} "
                f"function{'s' if len(funcs) != 1 else ''}/routine{'s' if len(funcs) != 1 else ''}: "
                + ', '.join(names[:25]) + (' …' if len(names) > 25 else '') + '.')
    if not summ and pars:
        summ = core.summarize(pars)
    kwtext = ' '.join(p for p in pars if isinstance(p, str))[:2_000_000]
    kwtext += ' ' + ' '.join(f"{f.get('name','')} {f.get('doc','')}" for f in funcs)
    kwtext += ' ' + ' '.join(o for o in outline if isinstance(o, str))[:200_000]
    kws = core.keywords(kwtext, r.get('keywords') or [])
    L.append('## Summary')
    L.append('')
    L.append(esc_par(summ) if summ else f'_No text content: {r.get("type") or kind} file._')
    L.append('')
    if kws:
        L.append('**Keywords:** ' + ' · '.join(kws))
        L.append('')

    # file facts
    L.append('## File')
    L.append('')
    L.append(f"- **Type:** {r.get('type') or kind}" + (f' (`.{ext}`)' if ext else ''))
    if r.get('title'):
        L.append(f"- **Title:** {r['title']}")
    L.append(f'- **Modified:** {wy(mt.year)} · {mt:%Y-%m-%d %H:%M}')
    L.append(f'- **Size:** {st.st_size:,} bytes')
    h = SHA.get(rel)
    if h:
        L.append(f'- **SHA-256:** `{h}`')
        others = [x for x in DUPS.get(h, []) if x != rel]
        if others:
            shown = ', '.join(link(rel_dir, o) for o in others[:10])
            more = f' … and {len(others) - 10} more' if len(others) > 10 else ''
            L.append(f'- **Identical copies elsewhere ({len(others)}):** {shown}{more}')
    for k, v in r.get('meta') or []:
        L.append(f'- **{k}:** {v}')
    L.append(f'- **Extracted by:** `{used}`')
    for n in r.get('notes') or []:
        L.append(f'- ⚠ {n}')
    L.append('')

    lang = r.get('code_lang', '')
    if funcs:
        L.append(f'## Functions ({len(funcs)})')
        L.append('')
        L.append('| # | Name | Kind | Line | Description |')
        L.append('|---|---|---|---|---|')
        for i, f in enumerate(funcs, 1):
            d = (f.get('doc') or '').replace('\n', ' ').replace('|', '\\|')[:160]
            L.append(f"| {i} | `{f.get('name','?')}` | {f.get('kind','function')} | {f.get('line','')} | {d} |")
        L.append('')
        for f in funcs:
            L.append(f"### `{f.get('name','?')}` — {f.get('kind','function')}" + (f" (line {f['line']})" if f.get('line') else ''))
            L.append('')
            if f.get('signature'):
                L.append(fence(f['signature'].strip(), lang))
                L.append('')
            if f.get('doc'):
                L.append(esc_par(f['doc'].strip()))
                L.append('')
            if f.get('params'):
                L.append('| Parameter | Type / direction | Note |')
                L.append('|---|---|---|')
                for p in f['params']:
                    p = list(p) + ['', '', '']
                    L.append('| `' + str(p[0]) + '` | ' + str(p[1]).replace('|', '\\|') + ' | ' + str(p[2]).replace('|', '\\|') + ' |')
                L.append('')
            if f.get('returns'):
                L.append(f"**Returns:** {f['returns']}")
                L.append('')
            if f.get('calls'):
                L.append('**Calls:** ' + ', '.join(f'`{c}`' for c in f['calls'][:60]))
                L.append('')

    if outline:
        L.append('## Structure')
        L.append('')
        for o in outline:
            if isinstance(o, dict):
                L.append(''); L.append(f"### {o.get('heading','')}"); L.append('')
            else:
                L.append(f'- {o}')
        L.append('')

    if pars:
        L.append('## Comments' if kind == 'source' else '## Full text')
        L.append('')
        used_chars = 0
        for p in pars:
            if isinstance(p, dict):
                L.append(f"### {p.get('heading','')}")
                L.append('')
                continue
            if used_chars > MAX_TEXT_CHARS:
                L.append(f'_… text truncated at {MAX_TEXT_CHARS:,} characters._')
                L.append('')
                break
            used_chars += len(p)
            L.append(esc_par(p))
            L.append('')
    L.append('---')
    L.append('_Sidecar generated by `shuffler_sidecars/run.py` · An archive by Anthony Peter Kuzub · WBSps.ca_')
    return '\n'.join(L) + '\n'

# ---------------------------------------------------------------- writing
OUT = None
MARK = b'Sidecar generated by `shuffler_sidecars/run.py`'


def process(path):
    try:
        r, used = run_extractor(path)
        md = render(path, r, used)
        rel = os.path.relpath(path, ROOT)
        dest_dir = ROOT if OUT is None else OUT
        dest = os.path.join(dest_dir, rel) + '.md'
        if len(os.path.basename(dest).encode()) > 255:
            return path, used, 'name-too-long'
        # never overwrite a .md we did not write (e.g. hand-written README.md next to a file named README)
        if os.path.exists(dest):
            with open(dest, 'rb') as f:
                f.seek(max(0, os.path.getsize(dest) - 400))
                ours = MARK in f.read()
            if not ours:
                dest = os.path.join(dest_dir, rel) + '.sidecar.md'
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, 'w', encoding='utf-8') as f:
            f.write(md)
        return path, used, 'ok'
    except Exception as e:
        return path, 'runner', f'error {e!r}'[:300]


def init(out):
    global OUT
    OUT = out
    load_extractors()
    load_hashes()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['hash', 'write', 'test'])
    ap.add_argument('--ext', default='')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--out', default=os.path.join(HERE, 'preview'))
    ap.add_argument('--jobs', type=int, default=os.cpu_count())
    a = ap.parse_args()
    if a.cmd == 'hash':
        return cmd_hash()
    files = list(all_files())
    out = None
    if a.cmd == 'test':
        exts = {('' if e.strip().lower() == '(none)' else e.strip().lower()) for e in a.ext.split(',') if e.strip()}
        if exts:
            files = [p for p in files if (os.path.basename(p).lower().rsplit('.', 1)[1] if '.' in os.path.basename(p) else '') in exts
                     or os.path.basename(p).lower() in exts]
        if a.limit:
            step = max(1, len(files) // a.limit)
            files = files[::step][:a.limit]
        out = a.out
    load_extractors()
    if LOAD_ERR:
        print('EXTRACTOR LOAD ERRORS:', *LOAD_ERR, sep='\n  ')
    t = time.time()
    stats = {}
    log = open(os.path.join(HERE, f'{a.cmd}_log.tsv') if a.cmd == 'write' else os.path.join(out, '_test_log.tsv'), 'w') if (a.cmd == 'write' or os.makedirs(out, exist_ok=True) or True) else None
    with Pool(a.jobs, initializer=init, initargs=(out,), maxtasksperchild=500) as pool:
        for i, (p, used, status) in enumerate(pool.imap_unordered(process, files, chunksize=8)):
            stats[(used, status.split(' ')[0])] = stats.get((used, status.split(' ')[0]), 0) + 1
            if status != 'ok' or a.cmd == 'test':
                log.write(f'{used}\t{status}\t{os.path.relpath(p, ROOT)}\n')
            if a.cmd == 'write' and i % 5000 == 0:
                print(f'{i}/{len(files)} {time.time()-t:.0f}s', flush=True)
    for k, v in sorted(stats.items(), key=lambda x: -x[1]):
        print(f'{v:8} {k[0]:28} {k[1]}')
    print(f'{len(files)} files in {time.time()-t:.0f}s')


if __name__ == '__main__':
    main()
