"""FPGA project / constraint / script / schematic-symbol files.

Altera Quartus II & MAX+PLUS II (qsf qpf qip qdf qar sdc tcl bsf bdf gdf tdf vwf scf
acf fit hif mif cdf jdi ppf), Xilinx ISE / CORE Generator (ucf ncf pcf xdc xco cgp cgc
xise gise ise prj xst spl tfi xaw ipf cpj), ModelSim (mpf mti do), Lattice lpf, plus a
few P-CAD/Gerber/report formats that share these extensions in the archive
(bsm bss bst tsm tss apr apr_lib sta) and misc binaries (qpw qws rlf).
"""
import os, re, zlib, time, collections
import core

EXTS = {'qsf', 'qpf', 'qip', 'qdf', 'qws', 'qar', 'sdc', 'ucf', 'xdc', 'ncf', 'pcf', 'tcl', 'bsf',
        'bdf', 'gdf', 'tdf', 'xco', 'xise', 'gise', 'ise', 'prj', 'xst', 'cdf', 'jdi', 'ppf', 'mpf',
        'mti', 'do', 'vwf', 'scf', 'acf', 'mif', 'coe', 'cgp', 'cgc', 'xaw', 'ipf', 'pin', 'sdc~',
        'qsf~', 'tcl~', 'apr', 'apr_lib', 'fit', 'rlf', 'tfi', 'hif', 'qpw', 'lpf', 'pdc', 'cpj',
        'spl', 'bsm', 'bss', 'bst', 'tsm', 'tss', 'sta'}

MAX_LINES = 5000
MAX_OUTLINE = 600

# ======================================================================== helpers

def _read(path, limit=40_000_000):
    t, trunc = core.read_text(path, limit)
    return t.replace('\r\n', '\n').replace('\r', '\n'), trunc


LIC = re.compile(
    r'^[^\n]*Copyright[^\n]*(?:Altera|Xilinx|Intel)[^\n]*\n(?:[^\n]*\n){0,70}?'
    r'[^\n]*(?:for further details\.|provided herein\.|AT ALL TIMES\.|in any way\.)[^\n]*',
    re.I | re.M)


def strip_license(text):
    """Replace vendor boilerplate copyright/licence comment blocks by a one-line marker."""
    def rep(m):
        first = m.group(0).split('\n', 1)[0].strip(' \t-#/*%')
        return f'[Standard licence header omitted: {first}]'
    return LIC.sub(rep, text[:400_000], count=4) + text[400_000:]


def text_pars(text, cap=MAX_LINES, chunk=40, lic=True):
    """Paragraphs on blank lines; long blocks chunked; licence boilerplate collapsed."""
    if lic:
        text = strip_license(text)
    lines = text.split('\n')
    trunc = len(lines) > cap
    lines = lines[:cap]
    pars, cur = [], []

    def flush():
        while cur:
            part = cur[:chunk]
            del cur[:chunk]
            pars.append('\n'.join(part))
    for ln in lines:
        if ln.strip():
            cur.append(ln.rstrip())
        else:
            flush()
    flush()
    return pars, trunc


def _cap_note(trunc, n=MAX_LINES):
    return [f'Full text capped at the first {n:,} lines.'] if trunc else []


def tcl_words(s):
    """Split one Tcl command into words (quotes/braces stripped, [..] kept)."""
    out, i, n = [], 0, len(s)
    while i < n:
        while i < n and s[i] in ' \t':
            i += 1
        if i >= n:
            break
        c = s[i]
        if c == '"':
            j = i + 1
            while j < n and s[j] != '"':
                j += 2 if s[j] == '\\' else 1
            out.append(s[i + 1:j]); i = j + 1
        elif c in '{[':
            close = '}' if c == '{' else ']'
            d, j = 0, i
            while j < n:
                if s[j] == '\\':
                    j += 2; continue
                if s[j] == c:
                    d += 1
                elif s[j] == close:
                    d -= 1
                    if d == 0:
                        break
                j += 1
            out.append(s[i + 1:j] if c == '{' else s[i:j + 1]); i = j + 1
        else:
            j = i
            while j < n and s[j] not in ' \t':
                if s[j] == '[':
                    d = 0
                    while j < n:
                        if s[j] == '[': d += 1
                        elif s[j] == ']':
                            d -= 1
                            if d == 0: break
                        j += 1
                j += 1
            out.append(s[i:j]); i = j
    return out


def logical_lines(text):
    """Join backslash continuations; yield (lineno, line) skipping pure comments."""
    buf, start = '', 0
    for no, ln in enumerate(text.split('\n'), 1):
        s = ln.rstrip()
        if not buf:
            start = no
        if s.endswith('\\'):
            buf += s[:-1] + ' '
            continue
        buf += s
        st = buf.strip()
        buf = ''
        if st and not st.startswith('#'):
            yield start, st


def _flag(words, name):
    for i, w in enumerate(words[:-1]):
        if w == name:
            return words[i + 1]
    return None


def _val(v):
    """Value of a Quartus assignment: '[file join $::quartus(qip_path) "x.v"]' -> 'x.v'."""
    if v.startswith('['):
        q = re.findall(r'"([^"]+)"', v)
        if q:
            return q[-1]
        w = v.strip('[]').split()
        return w[-1] if w else v
    return v


def _strings(data, minlen=3, cap=3000):
    out, seen = [], set()
    for m in re.finditer(rb'[\x20-\x7e]{%d,}' % minlen, data):
        s = m.group().decode('ascii').strip()
        if len(s) >= minlen and s not in seen:
            seen.add(s); out.append(s)
            if len(out) >= cap:
                break
    return out


def _ns(period):
    m = re.match(r'^\s*([\d\.eE+\-]+)\s*(ps|ns|us|ms|s)?\s*$', str(period or ''))
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    return v * {'ps': 1e-3, 'ns': 1, 'us': 1e3, 'ms': 1e6, 's': 1e9}[m.group(2) or 'ns']


def _mhz(period):
    p = _ns(period)
    if not p or p <= 0:
        return ''
    f = 1000.0 / p
    return f'{f:.4g} MHz' if f >= 1 else f'{f * 1000:.4g} kHz'


def _ini(text):
    secs, cur = collections.OrderedDict(), '(top)'
    for ln in text.split('\n'):
        s = ln.strip()
        if not s or s[0] in ';#':
            continue
        m = re.match(r'^\[(.+)\]$', s)
        if m:
            cur = m.group(1); secs.setdefault(cur, []); continue
        if '=' in s:
            k, v = s.split('=', 1)
            secs.setdefault(cur, []).append((k.strip(), v.strip()))
    return secs


def _lineno(text, pos):
    return text.count('\n', 0, pos) + 1

# ======================================================================== Quartus assignments

FILE_KEYS = re.compile(r'^(?:[A-Z_]*_FILE|SOURCE_FILE)$')
TIMING_KEYS = re.compile(r'FMAX|TSU|TCO|TPD|TH_|CLOCK|TIMING|TIMEQUEST|SDC|SETUP|HOLD|MULTICYCLE|CUT_OFF', re.I)


def quartus_parse(text):
    q = {'globals': collections.OrderedDict(), 'files': [], 'pins': collections.OrderedDict(),
         'iostd': {}, 'inst': collections.Counter(), 'inst_rows': [], 'timing': [],
         'other_cmds': collections.Counter(), 'n': 0, 'sections': collections.Counter()}
    for no, ln in logical_lines(text):
        if not ln.startswith('set_') and not ln.startswith('\tset_'):
            w0 = ln.split(None, 1)[0]
            q['other_cmds'][w0] += 1
            continue
        w = tcl_words(ln)
        if not w:
            continue
        cmd = w[0]
        q['n'] += 1
        if cmd == 'set_global_assignment':
            name = _flag(w, '-name') or ''
            v = _flag(w, '-value')
            if v is None:
                rest = [x for i, x in enumerate(w[1:], 1) if not x.startswith('-') and w[i - 1] not in
                        ('-name', '-section_id', '-entity', '-tag', '-comment', '-library', '-hdl_version')]
                v = rest[0] if rest else ''
            v = _val(v)
            sec = _flag(w, '-section_id')
            if sec:
                q['sections'][sec] += 1
            if FILE_KEYS.match(name):
                q['files'].append((name, v))
            else:
                if TIMING_KEYS.search(name):
                    q['timing'].append(f'{name} = {v}' + (f' (section {sec})' if sec else ''))
                if name not in q['globals']:
                    q['globals'][name] = v
                elif sec is None:
                    q['globals'][name] = v
        elif cmd == 'set_location_assignment':
            to = _flag(w, '-to') or ''
            loc = next((x for x in w[1:] if not x.startswith('-') and x != to), '')
            q['pins'][to] = loc
        elif cmd == 'set_instance_assignment':
            name = _flag(w, '-name') or ''
            to = _flag(w, '-to') or ''
            fr = _flag(w, '-from')
            rest = [x for i, x in enumerate(w[1:], 1) if not x.startswith('-') and w[i - 1] not in
                    ('-name', '-to', '-from', '-section_id', '-entity', '-tag', '-comment')]
            v = rest[0] if rest else ''
            q['inst'][name] += 1
            if name == 'IO_STANDARD':
                q['iostd'][to] = v
            elif name != 'CONNECT_TO_SLD_NODE_ENTITY_PORT' and len(q['inst_rows']) < 300:
                q['inst_rows'].append(f'{name} = {v} -> {to}' + (f' (from {fr})' if fr else ''))
            if TIMING_KEYS.search(name) and len(q['timing']) < 300:
                q['timing'].append(f'{name} = {v} -> {to}' + (f' (from {fr})' if fr else ''))
        else:
            q['other_cmds'][cmd] += 1
    return q


def quartus_report(q, r, kind_label):
    g = q['globals']
    fam, dev, top = g.get('FAMILY', ''), g.get('DEVICE', ''), g.get('TOP_LEVEL_ENTITY', '')
    ver = g.get('LAST_QUARTUS_VERSION') or g.get('ORIGINAL_QUARTUS_VERSION') or ''
    meta = r.setdefault('meta', [])
    for lab, k in (('Device family', 'FAMILY'), ('Device', 'DEVICE'), ('Top-level entity', 'TOP_LEVEL_ENTITY'),
                   ('Original Quartus version', 'ORIGINAL_QUARTUS_VERSION'),
                   ('Last Quartus version', 'LAST_QUARTUS_VERSION'),
                   ('Project created', 'PROJECT_CREATION_TIME_DATE'), ('IP tool', 'IP_TOOL_NAME'),
                   ('IP tool version', 'IP_TOOL_VERSION'), ('Configuration device', 'STRATIX_CONFIGURATION_DEVICE'),
                   ('Default I/O standard', 'STRATIX_DEVICE_IO_STANDARD')):
        if g.get(k):
            meta.append((lab, g[k]))
    if q['pins']:
        meta.append(('Pin assignments', len(q['pins'])))
    if q['files']:
        meta.append(('Source files', len(q['files'])))
    meta.append(('Assignment statements', q['n']))
    kw = [x for x in (top, dev, fam) if x]
    kw += [os.path.basename(v) for _, v in q['files'][:8]]
    r.setdefault('keywords', []).extend(kw)
    out = r.setdefault('outline', [])
    if q['files']:
        out.append({'heading': f"Source files ({len(q['files'])})"})
        for k, v in q['files'][:MAX_OUTLINE]:
            out.append(f'{k}: `{v}`')
    if q['pins']:
        out.append({'heading': f"Pin assignments ({len(q['pins'])})"})
        for sig, loc in list(q['pins'].items())[:MAX_OUTLINE * 2]:
            io = q['iostd'].get(sig)
            out.append(f'{loc} -> `{sig}`' + (f' ({io})' if io else ''))
    if q['iostd'] and not q['pins']:
        out.append({'heading': f"I/O standards ({len(q['iostd'])})"})
        for sig, v in list(q['iostd'].items())[:MAX_OUTLINE]:
            out.append(f'`{sig}`: {v}')
    if q['timing']:
        out.append({'heading': 'Timing settings'})
        out.extend(q['timing'][:200])
    if q['inst']:
        out.append({'heading': 'Instance assignment types'})
        for k, v in q['inst'].most_common(60):
            out.append(f'{k} ×{v}' + (' (SignalTap II node connections)' if k == 'CONNECT_TO_SLD_NODE_ENTITY_PORT' else ''))
        if q['inst_rows']:
            out.append({'heading': 'Instance assignments (other than pins / I/O standard / SignalTap)'})
            out.extend(f'`{x}`' for x in q['inst_rows'])
    others = [(k, v) for k, v in g.items() if not TIMING_KEYS.search(k)]
    if others:
        out.append({'heading': f'Global settings ({len(g)})'})
        for k, v in others[:400]:
            out.append(f'{k} = {v}')
    if q['sections']:
        out.append({'heading': 'Sections'})
        out.extend(f'{k} ({v} settings)' for k, v in q['sections'].most_common(50))
    # summary
    s = kind_label
    if ver:
        s = f'Quartus II {ver} ' + kind_label[0].lower() + kind_label[1:]
    if top:
        s += f' for top entity {top}'
    if dev or fam:
        s += ' on ' + ' '.join(x for x in (fam, dev) if x)
    parts = []
    if q['pins']:
        parts.append(f"{len(q['pins'])} pin assignments")
    if q['files']:
        parts.append(f"{len(q['files'])} source files")
    if not parts:
        parts.append(f"{q['n']} assignment statements")
    s += ' with ' + ' and '.join(parts)
    if g.get('IP_TOOL_NAME'):
        s += f" (IP: {g['IP_TOOL_NAME']} {g.get('IP_TOOL_VERSION', '')})".rstrip() + ''
    if q['inst'].get('CONNECT_TO_SLD_NODE_ENTITY_PORT'):
        s += f"; includes {q['inst']['CONNECT_TO_SLD_NODE_ENTITY_PORT']:,} SignalTap II node connections"
    return s + '.'


def ex_qsf(path, ext):
    text, trunc = _read(path)
    q = quartus_parse(text)
    label = {'qip': 'Quartus IP file (.qip)', 'qdf': 'Quartus default-assignments file (.qdf)'}.get(
        ext, 'Quartus settings file (.qsf)')
    r = {'kind': 'data', 'type': label, 'code_lang': 'tcl'}
    r['summary'] = quartus_report(q, r, 'Project settings' if ext.startswith('qsf') else
                                  ('IP file' if ext == 'qip' else 'Default-assignments file'))
    r['paragraphs'], t2 = text_pars(text)
    r['notes'] = _cap_note(t2 or trunc)
    return r


def ex_qpf(path, ext):
    text, trunc = _read(path)
    kv = dict(re.findall(r'^\s*([A-Z_]+)\s*=\s*"?([^"\n]*)"?', text, re.M))
    revs = re.findall(r'^\s*PROJECT_REVISION\s*=\s*"?([^"\n]*)"?', text, re.M)
    r = {'kind': 'data', 'type': 'Quartus II project file (.qpf)'}
    r['meta'] = [(k.replace('_', ' ').title(), v) for k, v in kv.items() if k != 'PROJECT_REVISION']
    r['meta'].append(('Revisions', ', '.join(revs)))
    r['outline'] = [f'Revision: {x}' for x in revs]
    r['keywords'] = revs
    r['summary'] = (f"Quartus II {kv.get('QUARTUS_VERSION', '')} project file".replace('  ', ' ') +
                    (f" with revision{'s' if len(revs) > 1 else ''} {', '.join(revs)}" if revs else '') +
                    (f", dated {kv['DATE'].strip()}" if kv.get('DATE') else '') + '.')
    r['paragraphs'], _ = text_pars(text)
    return r

# ======================================================================== SDC / XDC / Tcl

def sdc_parse(text):
    s = {'clocks': [], 'gclocks': [], 'pins': collections.OrderedDict(), 'iostd': {}, 'cmds': collections.Counter(),
         'paths': [], 'delays': []}
    for no, ln in logical_lines(text):
        ln = re.sub(r';\s*#.*$', '', ln)
        for part in ln.split(';'):
            w = tcl_words(part.strip())
            if not w:
                continue
            c = w[0]
            s['cmds'][c] += 1
            if c == 'create_clock':
                nm = _flag(w, '-name')
                per = _flag(w, '-period')
                tgt = [x for i, x in enumerate(w[1:], 1) if not x.startswith('-') and w[i - 1] not in
                       ('-name', '-period', '-waveform')]
                tg = ' '.join(tgt)
                s['clocks'].append((nm or tg, per or '', tg, no))
            elif c == 'create_generated_clock':
                nm = _flag(w, '-name')
                src = _flag(w, '-source') or ''
                ops = ' '.join(f'{k} {_flag(w, k)}' for k in ('-divide_by', '-multiply_by', '-phase', '-duty_cycle')
                               if _flag(w, k))
                tgt = [x for i, x in enumerate(w[1:], 1) if not x.startswith('-') and not w[i - 1].startswith('-')]
                s['gclocks'].append((nm or ' '.join(tgt), src, ops, no, ' '.join(tgt)))
            elif c == 'set_property':
                # XDC: set_property PACKAGE_PIN A3 [get_ports clk]  /  -dict {PACKAGE_PIN A3 IOSTANDARD LVCMOS33}
                tgt = w[-1] if len(w) > 2 else ''
                m = re.search(r'get_ports\s+\{?([^\]\}]+)', tgt)
                port = m.group(1).strip() if m else tgt
                if len(w) >= 4 and w[1] == '-dict':
                    d = w[2].split()
                    pairs = dict(zip(d[::2], d[1::2]))
                else:
                    pairs = {w[1]: w[2]} if len(w) >= 4 else {}
                for k, v in pairs.items():
                    if k.upper() in ('PACKAGE_PIN', 'LOC'):
                        s['pins'][port] = v
                    elif k.upper() == 'IOSTANDARD':
                        s['iostd'][port] = v
            elif c in ('set_input_delay', 'set_output_delay'):
                if len(s['delays']) < 200:
                    s['delays'].append(' '.join(w)[:200])
            elif c in ('set_false_path', 'set_multicycle_path', 'set_max_delay', 'set_min_delay', 'set_clock_groups'):
                if len(s['paths']) < 200:
                    s['paths'].append(' '.join(w)[:200])
    return s


def sdc_report(s, r):
    out = r.setdefault('outline', [])
    if s['clocks']:
        out.append({'heading': f"Clocks ({len(s['clocks'])})"})
        for nm, per, tg, no in s['clocks']:
            pn = _ns(per)
            out.append(f"`{nm}`: period {(f'{pn:g} ns' if pn is not None else per) or '?'}" + (f' ({_mhz(per)})' if _mhz(per) else '') +
                       (f' on {tg}' if tg and tg != nm else '') + f' (line {no})')
    if s['gclocks']:
        out.append({'heading': f"Generated clocks ({len(s['gclocks'])})"})
        for nm, src, ops, no, tg in s['gclocks']:
            out.append(f"`{nm}`" + (f' on {tg}' if tg and tg != nm else '') + (f' from {src}' if src else '') +
                       (f' {ops}' if ops else '') + f' (line {no})')
    if s['pins']:
        out.append({'heading': f"Pin locations ({len(s['pins'])})"})
        for p, v in list(s['pins'].items())[:MAX_OUTLINE * 2]:
            out.append(f'{v} -> `{p}`' + (f" ({s['iostd'][p]})" if p in s['iostd'] else ''))
    if s['delays']:
        out.append({'heading': 'I/O delays'}); out.extend(f'`{x}`' for x in s['delays'])
    if s['paths']:
        out.append({'heading': 'Path exceptions / clock groups'}); out.extend(f'`{x}`' for x in s['paths'])
    if s['cmds']:
        out.append({'heading': 'Commands used'})
        out.extend(f'{k} ×{v}' for k, v in s['cmds'].most_common(40))
    r.setdefault('keywords', []).extend([c[0] for c in s['clocks'][:6]])
    clk = ', '.join(f"{nm} ({_mhz(per) or per})" for nm, per, _, _ in s['clocks'][:6])
    parts = []
    if s['clocks']:
        parts.append(f"{len(s['clocks'])} clock{'s' if len(s['clocks']) != 1 else ''}: {clk}")
    if s['gclocks']:
        parts.append(f"{len(s['gclocks'])} generated clocks")
    if s['pins']:
        parts.append(f"{len(s['pins'])} pin locations")
    if s['paths']:
        parts.append(f"{len(s['paths'])} path exceptions")
    return '; '.join(parts)


def ex_sdc(path, ext):
    text, trunc = _read(path)
    s = sdc_parse(text)
    xdc = ext == 'xdc'
    r = {'kind': 'data', 'type': 'Xilinx Vivado design constraints (XDC)' if xdc else
         'Synopsys Design Constraints (SDC) timing constraints', 'code_lang': 'tcl'}
    body = sdc_report(s, r)
    r['summary'] = ('XDC constraints' if xdc else 'SDC timing constraints') + (f' defining {body}.' if body else
                                                                                 f" ({sum(s['cmds'].values())} commands).")
    r['paragraphs'], t2 = text_pars(text)
    r['notes'] = _cap_note(t2 or trunc)
    return r


TCL_CORE = {'set', 'if', 'else', 'elseif', 'foreach', 'for', 'while', 'return', 'incr', 'expr', 'switch', 'puts',
            'lappend', 'append', 'global', 'variable', 'upvar', 'catch', 'break', 'continue', 'proc', 'list',
            'lindex', 'llength', 'string', 'format', 'unset', 'info', 'array', 'concat', 'eval', 'then', 'error',
            'regexp', 'regsub', 'split', 'join', 'lsort', 'lsearch', 'lrange', 'file', 'open', 'close', 'gets',
            'namespace', 'uplevel', 'subst', 'source', 'package', 'default', '}', '{', ']'}


def _brace_end(text, i, cap=2_000_000):
    d, n = 0, min(len(text), i + cap)
    j = i
    while j < n:
        c = text[j]
        if c == '\\':
            j += 2; continue
        if c == '{':
            d += 1
        elif c == '}':
            d -= 1
            if d == 0:
                return j
        j += 1
    return n - 1


PROC = re.compile(r'^[ \t]*proc[ \t]+(\S+)[ \t]+', re.M)


def tcl_procs(text):
    funcs, spans = [], []
    lines = text.split('\n')
    for m in PROC.finditer(text):
        name = m.group(1)
        i = m.end()
        if i < len(text) and text[i] == '{':
            e = _brace_end(text, i); args = text[i + 1:e]; i = e + 1
        else:
            m2 = re.match(r'(\S+)', text[i:]); args = m2.group(1) if m2 else ''; i += len(args)
        while i < len(text) and text[i] in ' \t':
            i += 1
        body = ''
        if i < len(text) and text[i] == '{':
            e = _brace_end(text, i); body = text[i + 1:e]; spans.append((m.start(), e))
        ln = _lineno(text, m.start())
        # doc: comment lines just above
        doc, k = [], ln - 2
        while k >= 0 and lines[k].strip().startswith('#'):
            doc.insert(0, lines[k].strip().lstrip('#').strip()); k -= 1
        if not doc:  # or first comments in body
            for bl in body.split('\n')[:8]:
                bs = bl.strip()
                if bs.startswith('#'):
                    doc.append(bs.lstrip('#').strip())
                elif bs:
                    break
        params = []
        for a in tcl_words(args.replace('\n', ' ')):
            p = a.split(None, 1)
            params.append((p[0], 'arg', f'default {p[1]}' if len(p) > 1 else ''))
        calls = []
        for bl in body.split('\n'):
            bs = bl.strip()
            if not bs or bs.startswith('#'):
                continue
            w0 = re.match(r'([A-Za-z_:][\w:\.]*)', bs)
            for c in ([w0.group(1)] if w0 else []) + re.findall(r'\[\s*([A-Za-z_:][\w:\.]*)', bs):
                if c not in TCL_CORE and c not in calls:
                    calls.append(c)
        funcs.append({'name': name, 'kind': 'proc', 'line': ln,
                      'signature': f'proc {name} {{{args.strip()}}}',
                      'doc': '\n'.join(d for d in doc if d.strip('#=- '))[:1500],
                      'params': params, 'calls': calls[:60]})
    return funcs, spans


def ex_tcl(path, ext):
    text, trunc = _read(path)
    head = text[:3000]
    funcs, spans = tcl_procs(text)
    # top-level command usage
    cmds = collections.Counter()
    pos = 0
    for ln in text.split('\n'):
        inside = any(a <= pos <= b for a, b in spans) if spans else False
        pos += len(ln) + 1
        s = ln.strip()
        if inside or not s or s.startswith('#'):
            continue
        m = re.match(r'([A-Za-z_:][\w:\.\-]*)', s)
        if m:
            cmds[m.group(1)] += 1
    r = {'kind': 'source', 'code_lang': 'tcl', 'functions': funcs, 'outline': []}
    is_do = ext == 'do'
    kindtxt = 'Tcl script'
    if is_do:
        if re.search(r'ACCEL PCB|Auto-Generated DO File|\bbestsave\b|^\s*route\s+\d', head, re.M | re.I):
            kindtxt = 'Specctra / P-CAD ACCEL autorouter DO script'
            r['code_lang'] = ''
        else:
            kindtxt = 'ModelSim / Questa DO (Tcl) simulation script'
    elif re.search(r'^\s*(wcfg|isim)\b', text, re.M):
        kindtxt = 'Xilinx ISim simulator Tcl script'
    elif 'gui_sg_addsignal' in text or 'gui_open_db' in text:
        kindtxt = 'Synopsys VCS / DVE session Tcl script'
    elif 'xmdf' in text[:4000]:
        kindtxt = 'Xilinx CORE Generator XMDF Tcl package'
    elif re.search(r'planAhead|create_project|launch_runs', head):
        kindtxt = 'Xilinx PlanAhead / Vivado Tcl script'
    elif re.search(r'::quartus::|set_global_assignment|project_open|execute_flow', text[:20000]):
        kindtxt = 'Quartus II Tcl script'
    elif re.search(r'\bvsim\b|\bvlog\b|\bvcom\b|add wave', text[:20000]):
        kindtxt = 'ModelSim / simulator Tcl script'
    r['type'] = kindtxt
    extra = []
    if re.search(r'set_(global|location|instance)_assignment', text):
        q = quartus_parse(text)
        extra.append(quartus_report(q, r, 'Assignment script'))
    if re.search(r'create_clock|create_generated_clock|PACKAGE_PIN', text):
        s = sdc_parse(text)
        b = sdc_report(s, r)
        if b:
            extra.append('Constraints: ' + b + '.')
    if is_do and kindtxt.startswith('ModelSim'):
        comp = re.findall(r'^\s*(?:vlog|vcom)\b[^\n]*?([\w\-./\\$]+\.(?:v|vhd|vhdl|sv))', text, re.M)
        sim = re.findall(r'^\s*vsim\b([^\n]*)', text, re.M)
        run = re.findall(r'^\s*run\s+([^\n]*)', text, re.M)
        if comp:
            r['outline'].append({'heading': f'Compiled sources ({len(comp)})'})
            r['outline'].extend(f'`{c}`' for c in comp[:MAX_OUTLINE])
        if sim:
            extra.append('Simulates' + sim[0][:150] + '.')
        if run:
            extra.append(f'Run: {run[-1].strip()}.')
    if cmds:
        r['outline'].append({'heading': 'Top-level commands'})
        r['outline'].extend(f'{k} ×{v}' for k, v in cmds.most_common(40))
    # leading comment block as description
    hdr = []
    for ln in strip_license(text[:6000]).split('\n')[:40]:
        s = ln.strip()
        if s.startswith('#'):
            t = s.lstrip('#').strip().strip('-=*').strip()
            if t and not re.fullmatch(r'[\W_]+', t) and 'licence header omitted' not in t:
                hdr.append(t)
        elif s:
            break
    summ = kindtxt
    if funcs:
        summ += f" defining {len(funcs)} proc{'s' if len(funcs) != 1 else ''}: " + ', '.join(
            f['name'] for f in funcs[:20]) + (' …' if len(funcs) > 20 else '')
    elif cmds:
        summ += f" of {sum(cmds.values())} top-level commands (mostly {', '.join(k for k, _ in cmds.most_common(4))})"
    summ += '.'
    if hdr:
        summ += ' ' + ' '.join(hdr[:4])[:300]
    if extra:
        summ += ' ' + ' '.join(extra)
    r['summary'] = summ
    r['paragraphs'], t2 = text_pars(text)
    r['notes'] = _cap_note(t2 or trunc)
    return r

# ======================================================================== Xilinx UCF / NCF / PCF, Lattice LPF

def ex_ucf(path, ext):
    text, trunc = _read(path)
    clean = '\n'.join(re.sub(r'(#|//).*$', '', ln) for ln in text.split('\n'))
    pins, iostd, tnm, ts, groups, other = collections.OrderedDict(), {}, [], [], [], collections.Counter()
    freq = []
    for st in clean.split(';'):
        s = ' '.join(st.split())
        if not s:
            continue
        u = s.upper()
        kw = u.split(' ', 1)[0]
        other[kw] += 1
        m = re.match(r'(?:NET|INST|COMP|LOCATE COMP)\s+"?([^"\s]+)"?\s*(.*)$', s, re.I)
        if m:
            nm, rest = m.group(1), m.group(2)
            for item in rest.split('|'):
                mm = re.match(r'\s*(LOC|LOCATE\s*=\s*SITE|SITE)\s*=?\s*"?([^"\s]+)"?', item, re.I)
                if mm:
                    pins[nm] = mm.group(2)
                mm = re.match(r'\s*(IOSTANDARD|IO_TYPE)\s*=\s*"?([^"\s]+)"?', item, re.I)
                if mm:
                    iostd[nm] = mm.group(2)
                mm = re.match(r'\s*(TNM_NET|TNM)\s*=\s*"?([^"\s]+)"?', item, re.I)
                if mm:
                    tnm.append(f'{nm} -> timing group {mm.group(2)}')
                mm = re.match(r'\s*PERIOD\s*=\s*(.+)', item, re.I)
                if mm:
                    ts.append((nm, mm.group(1).strip()))
            continue
        m = re.match(r'(TIMESPEC\s+)?"?(TS[^"\s=]*)"?\s*=\s*(.+)$', s, re.I)
        if m:
            ts.append((m.group(2), m.group(3).strip())); continue
        m = re.match(r'(?:TIMEGRP|INST)\s+"?([^"\s]+)"?\s*=?\s*(.*)$', s, re.I)
        if m and kw == 'TIMEGRP':
            groups.append(f'{m.group(1)} = {m.group(2)[:150]}'); continue
        m = re.match(r'(FREQUENCY|PERIOD)\s+(?:NET|PORT)\s+"?([^"\s]+)"?\s+([\d\.]+)\s*(\w+)', s, re.I)
        if m:
            freq.append(f'{m.group(2)}: {m.group(3)} {m.group(4)}')
        m = re.match(r'IOBUF\s+PORT\s+"?([^"\s]+)"?\s+(.*)$', s, re.I)
        if m:
            mm = re.search(r'IO_TYPE\s*=\s*(\S+)', m.group(2), re.I)
            if mm:
                iostd[m.group(1)] = mm.group(1)
    names = {'ucf': 'Xilinx User Constraints File (UCF)', 'ncf': 'Xilinx Netlist Constraints File (NCF)',
             'pcf': 'Xilinx Physical Constraints File (PCF, written by MAP)',
             'lpf': 'Lattice Preference File (LPF)', 'pdc': 'Physical design constraints (PDC)'}
    r = {'kind': 'data', 'type': names.get(ext, 'FPGA constraints file'), 'outline': []}
    if ext == 'pcf' and not re.search(r'SCHEMATIC START|COMP\s+"', text[:5000]):
        r['type'] = 'Constraint / pin file (.pcf)'
    out = r['outline']
    clocks = []
    for nm, spec in ts:
        mm = re.search(r'([\d\.]+)\s*(ns|ps|us|MHz|kHz)', spec, re.I)
        if mm:
            v, u = float(mm.group(1)), mm.group(2).lower()
            f = {'ns': 1000 / v if v else 0, 'ps': 1e6 / v if v else 0, 'us': 1 / v if v else 0,
                 'mhz': v, 'khz': v / 1000}[u]
            clocks.append(f'{nm}: {spec[:120]} (~{f:.4g} MHz)')
        else:
            clocks.append(f'{nm}: {spec[:120]}')
    clocks += freq
    if clocks:
        out.append({'heading': f'Timing specs / clocks ({len(clocks)})'}); out.extend(clocks[:300])
    if tnm:
        out.append({'heading': f'Timing-group nets ({len(tnm)})'}); out.extend(tnm[:300])
    if groups:
        out.append({'heading': f'Timing groups ({len(groups)})'}); out.extend(groups[:300])
    if pins:
        out.append({'heading': f'Pin locations ({len(pins)})'})
        for nm, loc in list(pins.items())[:MAX_OUTLINE * 2]:
            out.append(f'{loc} -> `{nm}`' + (f' ({iostd[nm]})' if nm in iostd else ''))
    stds = collections.Counter(iostd.values())
    if stds:
        out.append({'heading': 'I/O standards'}); out.extend(f'{k} ×{v}' for k, v in stds.most_common())
    out.append({'heading': 'Statement types'}); out.extend(f'{k} ×{v}' for k, v in other.most_common(30))
    r['meta'] = [('Pin locations', len(pins)), ('Timing specs', len(clocks))]
    m = re.search(r'Written by:\s*([^\n]+)', text[:2000])
    if m:
        r['meta'].append(('Written by', m.group(1).strip()))
    parts = []
    if pins:
        parts.append(f'{len(pins)} pin locations')
    if clocks:
        parts.append(f'{len(clocks)} timing specs (' + '; '.join(c.split(' (')[0][:60] for c in clocks[:3]) + ')')
    if stds:
        parts.append('I/O standards ' + ', '.join(stds))
    r['summary'] = r['type'] + (' with ' + ', '.join(parts) if parts else '') + '.'
    r['keywords'] = list(stds)[:4]
    r['paragraphs'], t2 = text_pars(text)
    if ext == 'lpf' and len(r['paragraphs']) <= 3 and text.count(';') > 20:
        r['paragraphs'], t2 = text_pars(text.replace(';', ';\n'))
    r['notes'] = _cap_note(t2 or trunc)
    return r

# ======================================================================== Altera block symbols / diagrams

class Q(str):
    """Quoted string token in an S-expression."""


TOK = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def sexpr(text):
    stack = [[]]
    for m in TOK.finditer(text):
        t = m.group()
        if t == '(':
            stack.append([])
        elif t == ')':
            if len(stack) > 1:
                x = stack.pop(); stack[-1].append(x)
        elif t[0] == '"':
            stack[-1].append(Q(t[1:-1].replace('\\n', '\n').replace('\\"', '"')))
        else:
            stack[-1].append(t)
    while len(stack) > 1:
        x = stack.pop(); stack[-1].append(x)
    return stack[0]


def _ch(n, name):
    return [c for c in n if isinstance(c, list) and c and c[0] == name]


def _texts(n):
    return [c[1] for c in _ch(n, 'text') if len(c) > 1 and isinstance(c[1], str)]


def _dir(n):
    for c in n:
        if isinstance(c, list) and c and c[0] in ('input', 'output', 'bidir'):
            return c[0]
    return ''


def _ports(n):
    out = []
    for p in _ch(n, 'port'):
        t = _texts(p)
        out.append((t[0] if t else '?', _dir(p)))
    return out


def _params(n):
    out = []
    for p in _ch(n, 'parameter'):
        vals = [x for x in p[1:] if isinstance(x, Q)]
        if vals:
            out.append((vals[0], vals[1] if len(vals) > 1 else '', vals[3] if len(vals) > 3 else ''))
    return out


def _vrecords(data):
    out, seen = [], set()
    for m in re.finditer(rb'v([\x01-\xff])\x00', data):
        L = m.group(1)[0]
        b = data[m.end():m.end() + L]
        if len(b) == L and all(32 <= c < 127 for c in b):
            t = b.decode().strip()
            if t and t not in seen:
                seen.add(t); out.append(t)
                if len(out) > 4000:
                    break
    return out


def _gdf_like(path, ext, data):
    labels = _vrecords(data) if ext == 'gdf' else []
    if len(labels) < 3:
        labels = _strings(data, 2, 4000)
    labels = [s for s in labels if not re.match(r'^(Arial|Courier|Times|Helvetica)', s)]
    labels = [s for s in labels if re.match(r'^[A-Za-z0-9_\[\]\.\-~/: ,]+$', s) and len(s) < 80]
    sigs = [s for s in labels if re.match(r'^[A-Za-z_][\w\-~]*(\[[\d\.]+\])?$', s) and s not in ('GDF', 'SCF')]
    prims = [s for s in sigs if s.upper() in BDF_PRIM]
    sigs = [s for s in sigs if s.upper() not in BDF_PRIM]
    r = {'kind': 'data', 'outline': [{'heading': f'Text labels / names ({len(labels)})'}] + [f'`{x}`' for x in labels[:MAX_OUTLINE]]}
    if ext == 'gdf':
        r['type'] = 'MAX+PLUS II Graphic Design File (binary schematic)'
        r['summary'] = (f'MAX+PLUS II binary graphic design (schematic) file; {len(sigs)} signal/symbol names '
                        f"recovered, e.g. {', '.join(sigs[:20])}" +
                        (f"; primitives used: {', '.join(prims[:12])}" if prims else '') + '.')
    else:
        r['type'] = 'MAX+PLUS II Simulator Channel File (binary waveform vectors)'
        r['summary'] = (f'MAX+PLUS II binary simulation channel (waveform) file; signal names recovered: '
                        f"{', '.join(sigs[:20])}.")
    r['keywords'] = sigs[:8]
    r['paragraphs'] = [' · '.join(labels[i:i + 40]) for i in range(0, min(len(labels), 2000), 40)]
    r['notes'] = ['Binary MAX+PLUS II format: only embedded text strings were extracted.']
    return r


BDF_PRIM = {'VCC', 'GND', 'SOFT', 'NOT', 'AND2', 'AND3', 'AND4', 'OR2', 'OR3', 'OR4', 'NAND2', 'NOR2', 'XOR', 'XNOR',
            'DFF', 'DFFE', 'TFF', 'TFFE', 'JKFF', 'LCELL', 'WIRE', 'GLOBAL', 'CARRY', 'CASCADE', 'TRI', 'LATCH',
            'INPUT', 'OUTPUT', 'BIDIR', 'CONSTANT', 'OPNDRN', 'EXP', 'NAND3', 'NOR3', 'AND8', 'OR8', 'BUSMUX', '21MUX'}


def ex_bdf(path, ext):
    with open(path, 'rb') as f:
        data = f.read(60_000_000)
    if ext in ('gdf', 'scf') or b'\x00' in data[:2000]:
        if data[:3] in (b'GDF', b'SCF') or b'\x00' in data[:2000]:
            return _gdf_like(path, ext, data)
    text = data.decode('latin-1').replace('\r\n', '\n')
    hdr_comments = re.findall(r'/\*(.*?)\*/', text[:8000], re.S)
    body = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    tree = sexpr(body)
    hdr = _ch(tree, 'header')
    hkind = hdr[0][1] if hdr and len(hdr[0]) > 1 else ''
    ver = ''
    if hdr:
        v = _ch(hdr[0], 'version')
        ver = v[0][1] if v and len(v[0]) > 1 else ''
    stem = os.path.splitext(os.path.basename(path))[0]
    r = {'kind': 'source', 'code_lang': '', 'outline': [], 'meta': []}
    copy = next((c.strip() for c in hdr_comments if 'Copyright' in c), '')
    copy = re.search(r'Copyright[^\n]*', copy).group(0) if copy else ''
    pars = []
    if copy:
        pars.append(f'[Standard licence header omitted: {copy}]')
    warn = next((c.strip() for c in hdr_comments if 'WARNING' in c), '')
    if warn:
        pars.append(' '.join(warn.split()))
    if hkind == 'symbol' or ext == 'bsf':
        syms = _ch(tree, 'symbol')
        funcs = []
        for s in syms:
            t = _texts(s)
            name = t[0] if t else stem
            ports = _ports(s)
            prm = _params(s)
            cnt = collections.Counter(d for _, d in ports)
            funcs.append({'name': name, 'kind': 'block symbol', 'line': '',
                          'signature': f"{name}({', '.join(f'{d} {p}' for p, d in ports)})",
                          'doc': f"Quartus block symbol with {cnt['input']} input, {cnt['output']} output"
                                 f"{', %d bidir' % cnt['bidir'] if cnt['bidir'] else ''} ports"
                                 + (f' and {len(prm)} parameters' if prm else '') + '.',
                          'params': [(p, d, '') for p, d in ports] + [(n, 'parameter', f'= {v}' + (f' ({ty})' if ty else ''))
                                                                     for n, v, ty in prm]})
            for tx in t[2:]:
                pars.append(tx)
        r['type'] = 'Quartus block symbol file (.bsf)'
        r['functions'] = funcs
        if funcs:
            f0 = funcs[0]
            r['summary'] = f"Quartus II block symbol for `{f0['name']}`: " + f0['doc'][len('Quartus block symbol with '):].rstrip('.') + \
                           ' (' + ', '.join(f'{p} ({d})' for p, d, _ in f0['params'][:30]) + ').'
            r['keywords'] = [f['name'] for f in funcs]
        else:
            r['summary'] = 'Quartus block symbol file with no symbol definition found.'
        if ver:
            r['meta'].append(('Symbol format version', ver))
        pars += [f"{f['name']}: " + ', '.join(f'{p} [{d}]' for p, d, _ in f['params']) for f in funcs]
        r['paragraphs'] = pars
        return r
    # block diagram
    pins = []
    for p in _ch(tree, 'pin'):
        t = _texts(p)
        nm = t[1] if len(t) > 1 else (t[0] if t else '?')
        pins.append((nm, _dir(p)))
    insts, types = [], collections.Counter()
    for kind in ('symbol', 'block'):
        for s in _ch(tree, kind):
            t = _texts(s)
            typ = t[0] if t else '?'
            inst = t[1] if len(t) > 1 else ''
            prm = _params(s)
            types[typ] += 1
            insts.append((typ, inst, kind, prm, len(_ports(s))))
    nets = collections.Counter()
    nconn = 0
    for c in _ch(tree, 'connector'):
        nconn += 1
        for t in _texts(c):
            nets[t] += 1
    notes_txt = [t for c in tree if isinstance(c, list) and c and c[0] == 'text' for t in c[1:2]
                 if isinstance(t, str) and len(re.findall(r'[A-Za-z0-9]', t)) >= 2]
    cnt = collections.Counter(d for _, d in pins)
    r['type'] = 'Quartus block diagram / schematic file (.bdf)'
    r['meta'] += [('Top-level pins', len(pins)), ('Instances', len(insts)), ('Connectors (wires/buses)', nconn)]
    if ver:
        r['meta'].append(('BDF format version', ver))
    r['functions'] = [{'name': stem, 'kind': 'block diagram', 'line': '',
                       'doc': f"Top-level schematic with {cnt['input']} inputs, {cnt['output']} outputs"
                              f"{', %d bidirs' % cnt['bidir'] if cnt['bidir'] else ''}; instantiates "
                              f"{len(insts)} blocks of {len(types)} types.",
                       'params': [(p, d, '') for p, d in pins],
                       'calls': [k for k, _ in types.most_common()]}]
    out = r['outline']
    if pins:
        out.append({'heading': f'Pins ({len(pins)})'})
        out.extend(f'{d or "pin"}: `{p}`' for p, d in pins[:MAX_OUTLINE * 2])
    if insts:
        out.append({'heading': f'Block types used ({len(types)})'})
        out.extend(f'`{k}` ×{v}' for k, v in types.most_common(200))
        out.append({'heading': f'Instances ({len(insts)})'})
        for typ, inst, kind, prm, np_ in insts[:MAX_OUTLINE * 2]:
            ps = ', '.join(f'{n}={v}' for n, v, _ in prm[:12])
            out.append(f'`{inst}`: {typ} ({kind}, {np_} ports)' + (f' [{ps}]' if ps else ''))
    if nets:
        out.append({'heading': f'Named wires / buses ({len(nets)})'})
        out.extend(f'`{k}`' for k in list(nets)[:MAX_OUTLINE * 2])
    order = sorted(types, key=lambda k: (k.upper() in BDF_PRIM, -types[k]))
    r['keywords'] = order[:8]
    r['summary'] = (f"Quartus II block diagram `{stem}` with {len(pins)} top-level pins ({cnt['input']} in, "
                    f"{cnt['output']} out" + (f", {cnt['bidir']} bidir" if cnt['bidir'] else '') +
                    f"), {len(insts)} instances of {len(types)} block types (" +
                    ', '.join(order[:12]) + f') and {nconn} connectors.')
    if notes_txt:
        r['summary'] += f' Annotations include: ' + '; '.join(n.replace('\n', ' ')[:60] for n in notes_txt[:5]) + '.'
    pars += [{'heading': 'Schematic annotations'}] + notes_txt if notes_txt else []
    if not notes_txt:
        pars.append('Pins: ' + ', '.join(f'{p} ({d})' for p, d in pins[:400]))
    r['paragraphs'] = pars
    return r

# ======================================================================== AHDL .tdf

AHDL_PRIM = {'DFF', 'DFFE', 'DFFEA', 'TFF', 'TFFE', 'JKFF', 'JKFFE', 'SRFF', 'SRFFE', 'LATCH', 'NODE',
             'TRI_STATE_NODE', 'SOFT', 'LCELL', 'CARRY', 'CASCADE', 'GLOBAL', 'EXP', 'MCELL', 'TRI', 'OPNDRN',
             'MACHINE', 'CARRY_SUM', 'WIRE', 'ROW_GLOBAL', 'EXPDFF', 'ALT_INBUF', 'ALT_OUTBUF', 'ALT_IOBUF'}

AHDL_KW = {'FOR', 'IF', 'GENERATE', 'ELSE', 'END', 'IN', 'TO', 'THEN', 'BEGIN', 'CASE', 'WITH'}

AHDL_COMMENT = re.compile(r'"[^"\n]*"|--[^\n]*|%[^%]*%')


def _ahdl_clean(text):
    def rep(m):
        s = m.group(0)
        if s[0] == '"':
            return s
        return re.sub(r'[^\n]', ' ', s)
    return AHDL_COMMENT.sub(rep, text)


def _paren_block(text, i):
    """text[i] == '(' -> (inner, end_index)."""
    d = 0
    for j in range(i, min(len(text), i + 500_000)):
        if text[j] == '(':
            d += 1
        elif text[j] == ')':
            d -= 1
            if d == 0:
                return text[i + 1:j], j
    return text[i + 1:], len(text) - 1


def _ahdl_ports(s):
    out = []
    for decl in s.split(';'):
        decl = ' '.join(decl.split())
        if ':' not in decl:
            continue
        names, typ = decl.rsplit(':', 1)
        typ = typ.strip()
        dflt = ''
        if '=' in typ:
            typ, dflt = [x.strip() for x in typ.split('=', 1)]
        for n in re.split(r',(?![^\[]*\])', names):
            n = n.strip()
            if n:
                out.append((n, typ, f'default {dflt}' if dflt else ''))
    return out


def ex_tdf(path, ext):
    text, trunc = _read(path)
    clean = _ahdl_clean(text)
    raw_lines = text.split('\n')
    r = {'kind': 'source', 'type': 'AHDL design file (Altera Hardware Description Language)',
         'code_lang': 'ahdl', 'outline': [], 'meta': []}
    gen = []
    m = re.search(r'megafunction wizard:\s*%([^%\n]+)%', text[:3000])
    if m:
        gen.append(f'MegaWizard-generated wrapper for {m.group(1).strip()}')
    base = os.path.basename(path).lower()
    lib = re.match(r'(lpm_|alt|scfifo|dcfifo|a_|dffpipe|stratix|cyclone|sld_)', base) and 'Altera' in text[:5000] \
        and not re.search(r'[/\\]db[/\\]', path)
    if not lib and (re.search(r'Clearbox|clearbox|CBX_', text[:4000]) or re.search(r'[/\\]db[/\\]', path)):
        gen.append('Quartus-generated (clearbox / db) megafunction implementation')
    if lib and not gen:
        gen.append('Altera megafunction library source (lpm/alt*), shipped with Quartus/MAX+PLUS II')
    incs = re.findall(r'\bINCLUDE\s+"([^"]+)"', clean, re.I)
    consts = re.findall(r'\bCONSTANT\s+(\w+)\s*=\s*([^;]+);', clean, re.I)
    protos = []
    for pm in re.finditer(r'\bFUNCTION\s+(\w+)\s*\(', clean, re.I):
        inner, e = _paren_block(clean, pm.end() - 1)
        rest = clean[e + 1:e + 4000]
        rm = re.match(r'\s*(?:WITH\s*\(([^)]*)\)\s*)?RETURNS\s*\(([^)]*)\)', rest, re.I | re.S)
        protos.append((pm.group(1), ' '.join(inner.split()),
                       ' '.join(rm.group(1).split()) if rm and rm.group(1) else '',
                       ' '.join(rm.group(2).split()) if rm else '', _lineno(clean, pm.start())))
    params = []
    for pm in re.finditer(r'\bPARAMETERS\s*\(', clean, re.I):
        inner, _ = _paren_block(clean, pm.end() - 1)
        for p in re.split(r',(?![^\(]*\))', inner):
            p = ' '.join(p.split())
            if p:
                params.append(p)
    subs = list(re.finditer(r'\bSUBDESIGN\s+(\w+)\s*\(', clean, re.I))
    funcs = []
    for i, sm in enumerate(subs):
        name = sm.group(1)
        inner, e = _paren_block(clean, sm.end() - 1)
        ports = _ahdl_ports(inner)
        seg = clean[e:subs[i + 1].start() if i + 1 < len(subs) else len(clean)]
        vm = re.search(r'\bVARIABLE\b(.*?)\bBEGIN\b', seg, re.S | re.I)
        calls, varrows = [], []
        if vm:
            for decl in re.split(r';', vm.group(1)):
                d = ' '.join(decl.split())
                mm = re.match(r'(.+?)\s*:\s*(\w+)\b(.*)$', d)
                if mm:
                    typ = mm.group(2)
                    varrows.append(f'{mm.group(1)} : {typ}{mm.group(3)[:120]}')
                    if typ.upper() not in AHDL_PRIM and typ.upper() not in AHDL_KW and typ not in calls:
                        calls.append(typ)
        ln = _lineno(clean, sm.start())
        doc, k = [], ln - 2
        while k >= 0 and (raw_lines[k].strip().startswith('--') or not raw_lines[k].strip()) and len(doc) < 30:
            s = raw_lines[k].strip().lstrip('-').strip()
            if s:
                doc.insert(0, s)
            k -= 1
        doc = [d for d in doc if not re.fullmatch(r'[=*\-_ ]+', d)]
        if any('Copyright' in d or 'megafunction design' in d for d in doc):
            doc = []
        cnt = collections.Counter(t.split()[0].upper() if t.split() else '' for _, t, _ in ports)
        dsum = (f"AHDL subdesign with {cnt['INPUT']} input{'s' if cnt['INPUT'] != 1 else ''}, "
                f"{cnt['OUTPUT']} output{'s' if cnt['OUTPUT'] != 1 else ''}" +
                (f", {cnt['BIDIR']} bidirs" if cnt['BIDIR'] else '') +
                (f"; instantiates {', '.join(calls[:10])}" if calls else '') + '.')
        funcs.append({'name': name, 'kind': 'SUBDESIGN', 'line': ln,
                      'signature': f"SUBDESIGN {name}\n(\n" + '\n'.join(f'\t{n} : {t};' for n, t, _ in ports) + '\n)',
                      'doc': ('\n'.join(doc[-12:]) + '\n\n' if doc else '') + dsum, 'params': ports, 'calls': calls})
        if varrows:
            r['outline'].append({'heading': f'VARIABLE section of {name} ({len(varrows)})'})
            r['outline'].extend(f'`{v}`' for v in varrows[:300])
    for nm, args, w, ret, ln in protos:
        funcs.append({'name': nm, 'kind': 'FUNCTION prototype', 'line': ln,
                      'signature': f'FUNCTION {nm} ({args})' + (f' WITH ({w})' if w else '') + f' RETURNS ({ret});',
                      'doc': 'Function prototype (interface of a lower-level design).',
                      'params': [(a.strip(), 'input', '') for a in args.split(',') if a.strip()] +
                                [(a.strip(), 'output', '') for a in ret.split(',') if a.strip()]})
    r['functions'] = funcs
    if incs:
        r['outline'].insert(0, {'heading': f'INCLUDE files ({len(incs)})'})
        r['outline'][1:1] = [f'`{x}`' for x in incs]
    if params:
        r['outline'].append({'heading': f'PARAMETERS ({len(params)})'}); r['outline'].extend(f'`{p}`' for p in params[:300])
    if consts:
        r['outline'].append({'heading': f'CONSTANTs ({len(consts)})'})
        r['outline'].extend(f'`{a} = {b.strip()}`' for a, b in consts[:300])
    retr = re.findall(r'Retrieval info:\s*([^\n]+)', text)
    if retr:
        r['outline'].append({'heading': f'MegaWizard retrieval info ({len(retr)})'})
        r['outline'].extend(f'`{x.strip()}`' for x in retr[:200])
    if gen:
        r['meta'].append(('Origin', '; '.join(gen)))
        r['notes'] = [gen[0] + ' — not hand-written design code.']
    m = re.search(r'Copyright[^\n]*', text[:5000])
    if m:
        r['meta'].append(('Copyright', m.group(0).strip(' -%')))
    subn = [f['name'] for f in funcs if f['kind'] == 'SUBDESIGN']
    s = 'AHDL design file'
    if subn:
        s += f" defining SUBDESIGN {', '.join(subn[:6])}" + (' …' if len(subn) > 6 else '')
        f0 = funcs[0]
        s += f" ({f0['doc'].split(chr(10))[-1][len('AHDL subdesign with '):].rstrip('.')})"
    if protos:
        s += f'; declares {len(protos)} function prototype{"s" if len(protos) != 1 else ""}'
    if incs:
        s += f"; includes {', '.join(incs[:6])}"
    s += '.'
    if gen:
        s += ' ' + '; '.join(gen) + '.'
    r['summary'] = s
    r['keywords'] = subn[:4] + [p[0] for p in protos[:4]]
    r['paragraphs'], t2 = text_pars(text)
    r['notes'] = r.get('notes', []) + _cap_note(t2 or trunc)
    return r

# ======================================================================== Xilinx CORE Generator / ISE

def ex_xco(path, ext):
    text, trunc = _read(path)
    sets, csets, sel = collections.OrderedDict(), collections.OrderedDict(), []
    for ln in text.split('\n'):
        s = ln.strip()
        m = re.match(r'^SET\s+(\S+)\s*=\s*(.*)$', s, re.I)
        if m:
            sets[m.group(1)] = m.group(2); continue
        m = re.match(r'^CSET\s+(\S+?)\s*=\s*(.*)$', s, re.I)
        if m:
            csets[m.group(1)] = m.group(2); continue
        m = re.match(r'^SELECT\s+(.+)$', s, re.I)
        if m:
            sel.append(m.group(1))
    gen = re.search(r'#\s*(Xilinx CORE Generator[^\n]*)', text)
    r = {'kind': 'data', 'type': 'Xilinx CORE Generator ' + ('project options (.cgp)' if ext == 'cgp' else 'core configuration (.xco)'),
         'outline': [], 'meta': []}
    core_name = ver = ''
    if sel:
        p = sel[0].split()
        core_name = p[0]
        ver = p[-1] if len(p) > 1 else ''
        r['meta'].append(('Core', sel[0]))
    comp = csets.get('component_name', '')
    for lab, k in (('Device', 'device'), ('Family', 'devicefamily'), ('Package', 'package'),
                   ('Speed grade', 'speedgrade'), ('Design entry', 'designentry'), ('Flow vendor', 'flowvendor')):
        if sets.get(k):
            r['meta'].append((lab, sets[k]))
    if comp:
        r['meta'].append(('Component name', comp))
    if gen:
        r['meta'].append(('Generator', gen.group(1).strip()))
    if csets:
        r['outline'].append({'heading': f'Core parameters (CSET, {len(csets)})'})
        r['outline'].extend(f'{k} = {v}' for k, v in list(csets.items())[:MAX_OUTLINE])
    if sets:
        r['outline'].append({'heading': f'Project options (SET, {len(sets)})'})
        r['outline'].extend(f'{k} = {v}' for k, v in sets.items())
    dev = ' '.join(x for x in (sets.get('device', ''), sets.get('package', ''), sets.get('speedgrade', '')) if x)
    if ext == 'cgp':
        r['summary'] = f"Xilinx CORE Generator project options for {sets.get('devicefamily', '?')} {dev}".rstrip() + '.'
    else:
        keyp = [f'{k}={v}' for k, v in csets.items() if re.search(r'width|depth|clock|freq|type|memory|coef|implementation', k, re.I)][:8]
        r['summary'] = (f"Xilinx CORE Generator configuration of `{comp or '?'}` using {core_name.replace('_', ' ')} "
                        f"v{ver} for {sets.get('devicefamily', '?')} {dev}" + (f"; key settings: {', '.join(keyp)}" if keyp else '') + '.')
    r['keywords'] = [x for x in (comp, core_name, sets.get('device', '')) if x]
    r['paragraphs'], t2 = text_pars(text)
    r['notes'] = _cap_note(t2 or trunc)
    return r


def _xml_root(text):
    import xml.etree.ElementTree as ET
    try:
        return ET.fromstring(text.encode('utf-8', 'replace') if isinstance(text, str) else text)
    except Exception:
        try:
            return ET.fromstring(re.sub(r'<\?xml[^>]*\?>', '', text).encode('utf-8', 'replace'))
        except Exception:
            return None


def _ln(tag):
    return tag.rsplit('}', 1)[-1]


def _attr(e, name):
    for k, v in e.attrib.items():
        if _ln(k) == name:
            return v
    return None


def _xml_pars(root, cap=5000):
    out = []
    for e in root.iter():
        a = ' '.join(f'{_ln(k)}="{v}"' for k, v in e.attrib.items())
        t = (e.text or '').strip()
        if a or t:
            out.append(f'<{_ln(e.tag)}> ' + a + (f' : {t}' if t else ''))
        if len(out) >= cap:
            break
    return out


def ex_xml(path, ext):
    text, trunc = _read(path)
    root = _xml_root(text)
    r = {'kind': 'data', 'outline': [], 'meta': []}
    if root is None:
        r['type'] = 'XML file (unparseable)'
        r['paragraphs'], _ = text_pars(text)
        r['notes'] = ['XML could not be parsed; raw text shown.']
        return r
    tag = _ln(root.tag)
    stem = os.path.splitext(os.path.basename(path))[0]
    if ext == 'xise' or tag == 'project':
        r['type'] = 'Xilinx ISE Project Navigator project (.xise)'
        v = next((e for e in root.iter() if _ln(e.tag) == 'version'), None)
        isev = _attr(v, 'ise_version') if v is not None else ''
        files = [(_attr(e, 'name'), _attr(e, 'type'),
                  ', '.join(sorted({_attr(a, 'name') for a in e if _ln(a.tag) == 'association'} - {None})))
                 for e in root.iter() if _ln(e.tag) == 'file']
        props = [(_attr(e, 'name'), _attr(e, 'value'), _attr(e, 'valueState')) for e in root.iter() if _ln(e.tag) == 'property']
        pd = {k: v for k, v, _ in props}
        r['meta'] += [('ISE version', isev)] + [(k, pd[k]) for k in ('Device Family', 'Device', 'Package', 'Speed Grade',
                                                                         'Implementation Top', 'Preferred Language',
                                                                         'Synthesis Tool', 'Simulator') if pd.get(k)]
        r['outline'].append({'heading': f'Source files ({len(files)})'})
        r['outline'].extend(f'`{n}` ({t})' + (f' — {a}' if a else '') for n, t, a in files[:MAX_OUTLINE])
        nd = [(k, v) for k, v, s in props if s == 'non-default']
        r['outline'].append({'heading': f'Non-default properties ({len(nd)} of {len(props)})'})
        r['outline'].extend(f'{k} = {v}' for k, v in nd[:MAX_OUTLINE])
        bind = [(_attr(e, 'name'), _attr(e, 'x')) for e in root.iter() if _ln(e.tag) == 'binding']
        if bind:
            r['outline'].append({'heading': 'Bindings'}); r['outline'].extend(f'{a} -> {b}' for a, b in bind)
        top = (pd.get('Implementation Top') or '').split('|')[-1]
        r['summary'] = (f"Xilinx ISE {isev} project" + (f' for top module {top}' if top else '') +
                        f" on {pd.get('Device Family', '?')} {pd.get('Device', '')}{pd.get('Speed Grade', '')}-{pd.get('Package', '')}"
                        f" with {len(files)} source files and {len(nd)} non-default properties.")
        r['keywords'] = [x for x in (top, pd.get('Device'), pd.get('Device Family')) if x] + \
                        [os.path.basename(n or '') for n, _, _ in files[:6]]
    elif ext == 'gise' or tag == 'generated_project':
        r['type'] = 'Xilinx ISE generated-project status file (.gise)'
        v = next((e.text for e in root.iter() if _ln(e.tag) == 'version'), '')
        sp = next((_attr(e, 'name') for e in root.iter() if _ln(e.tag) == 'sourceproject'), '')
        files = [(_attr(e, 'name'), _attr(e, 'fileType'), _attr(e, 'origination')) for e in root.iter() if _ln(e.tag) == 'file']
        tr = [(_attr(e, 'name'), _attr(e, 'state') or ', '.join(_attr(x, 'value') or (x.text or '').strip() for x in e
                                                              if _ln(x.tag) == 'status'), _attr(e, 'result'))
              for e in root.iter() if _ln(e.tag) == 'transform']
        r['meta'] += [('Schema version', v), ('Source project', sp), ('Generated files', len(files)), ('Transforms', len(tr))]
        r['outline'].append({'heading': f'Generated files ({len(files)})'})
        r['outline'].extend(f'`{n}` ({t}, {o})' for n, t, o in files[:MAX_OUTLINE])
        if tr:
            r['outline'].append({'heading': f'Process transforms ({len(tr)})'})
            r['outline'].extend(f'{n}' + (f': {s}' if s else '') + (f' ({res})' if res else '') for n, s, res in tr[:MAX_OUTLINE])
        r['summary'] = (f'Xilinx ISE Project Navigator generated-file tracking for {sp or stem}: {len(files)} generated files, '
                        f'{len(tr)} process transforms' + (f" ({', '.join(sorted({x for _, s, _ in tr for x in (s or '').split(', ') if x}))})"
                                                       if any(s for _, s, _ in tr) else '') + '.')
    elif tag == 'pinplan':
        r['type'] = 'Quartus MegaWizard pin plan (.ppf)'
        pins = [(_attr(e, 'name'), _attr(e, 'direction'), _attr(e, 'source')) for e in root.iter() if _ln(e.tag) == 'pin']
        r['meta'] += [('Family', _attr(root, 'intended_family')), ('Megafunction', _attr(root, 'megafunction_name')),
                      ('Variation', _attr(root, 'variation_name'))]
        r['outline'].append({'heading': f'Ports ({len(pins)})'})
        r['outline'].extend(f'`{n}` {d}' + (f' ({s})' if s else '') for n, d, s in pins)
        r['summary'] = (f"Quartus pin plan for {_attr(root, 'megafunction_name')} variation `{_attr(root, 'variation_name')}` "
                        f"({_attr(root, 'intended_family')}) with {len(pins)} ports: " + ', '.join(n or '' for n, _, _ in pins[:20]) + '.')
        r['keywords'] = [x for x in (_attr(root, 'variation_name'), _attr(root, 'megafunction_name')) if x]
    elif tag == 'sld_project_info':
        r['type'] = 'Quartus JTAG debugging information (.jdi)'
        files = [(_attr(e, 'path'), _attr(e, 'device'), _attr(e, 'checksum')) for e in root.iter() if _ln(e.tag) == 'file']
        r['outline'].append({'heading': 'Programming files'})
        r['outline'].extend(f'`{p}`' + (f' for {d}' if d else '') + (f' checksum {c}' if c else '') for p, d, c in files)
        nodes = [e.attrib for e in root.iter() if _ln(e.tag) == 'node']
        if nodes:
            r['outline'].append({'heading': f'Debug nodes ({len(nodes)})'})
            r['outline'].extend(str(dict(n))[:200] for n in nodes[:200])
        devs = sorted({d for _, d, _ in files if d})
        r['summary'] = f"Quartus JTAG debug info listing {len(files)} programming files ({', '.join(p or '' for p, _, _ in files)}) for {', '.join(devs)}."
        r['keywords'] = devs
    else:
        r['type'] = {'cgc': 'Xilinx CORE Generator project components (SPIRIT/IP-XACT XML)'}.get(ext, f'XML ({tag})')
        insts = [e for e in root.iter() if _ln(e.tag) == 'componentInstance']
        for ci in insts:
            nm = next((x.text for x in ci.iter() if _ln(x.tag) == 'instanceName'), '?')
            ref = next((x for x in ci.iter() if _ln(x.tag) == 'componentRef'), None)
            refs = ' '.join(f'{_ln(k)}={v}' for k, v in (ref.attrib.items() if ref is not None else []))
            vals = [(_attr(x, 'referenceId'), (x.text or '').strip()) for x in ci.iter() if _ln(x.tag) == 'configurableElementValue']
            r['outline'].append({'heading': f'Instance {nm}'})
            if refs:
                r['outline'].append(refs)
            r['outline'].extend(f'{a} = {b}' for a, b in vals[:300])
        r['summary'] = (f'{r["type"]} with {len(insts)} component instance(s): ' +
                        ', '.join(next((x.text or '' for x in ci.iter() if _ln(x.tag) == 'instanceName'), '?') for ci in insts[:10]) + '.') \
            if insts else f'{r["type"]} file with root element <{tag}>.'
    r['paragraphs'] = _xml_pars(root)
    if trunc:
        r['notes'] = ['File truncated while reading.']
    return r


def ex_prj(path, ext):
    text, trunc = _read(path)
    r = {'kind': 'data', 'outline': [], 'meta': []}
    hdl = [(l or {'.v': 'verilog', '.sv': 'verilog', '.vhd': 'vhdl', '.vhdl': 'vhdl'}.get(os.path.splitext(f)[1].lower(), ''), b, f)
           for l, b, f in re.findall(r'^[ \t]*(?:(verilog|vhdl|vhdl\w*)[ \t]+)?(\w+)[ \t]+"?([^"\s]+\.\w+)"?[ \t]*$', text, re.M)]
    if hdl and len(hdl) >= max(1, len([l for l in text.split('\n') if l.strip() and not l.strip().startswith('#')]) // 2):
        r['type'] = 'Xilinx XST synthesis project (.prj source list)'
        r['outline'].append({'heading': f'Sources ({len(hdl)})'})
        r['outline'].extend(f"`{f}` ({lang or 'hdl'}, library {lib})" for lang, lib, f in hdl)
        langs = collections.Counter(l or 'hdl' for l, _, _ in hdl)
        gen = re.search(r'Generated by\s+([^\n]+)', text)
        r['summary'] = (f'XST project file listing {len(hdl)} HDL sources (' + ', '.join(f'{v} {k}' for k, v in langs.items()) +
                        ') compiled into library ' + ', '.join(sorted({l for _, l, _ in hdl})) + ': ' +
                        ', '.join(os.path.basename(f) for _, _, f in hdl[:12]) + (' …' if len(hdl) > 12 else '') + '.' +
                        (f' {gen.group(0).strip()}.' if gen else ''))
        r['keywords'] = [os.path.splitext(os.path.basename(f))[0] for _, _, f in hdl[:8]]
    elif re.search(r'^\s*(set_option|add_file|impl\s+-add|project\s+-)', text, re.M):
        r['type'] = 'Synplify synthesis project (.prj, Tcl)'
        opts = re.findall(r'^\s*set_option\s+-(\S+)\s+(.*)$', text, re.M)
        files = re.findall(r'^\s*add_file\s+(?:-\w+\s+)*"?([^"\n]+)"?', text, re.M)
        od = dict(opts)
        r['meta'] += [(k.title(), od[k]) for k in ('technology', 'part', 'package', 'speed_grade', 'top_module', 'frequency') if k in od]
        r['outline'].append({'heading': f'Source files ({len(files)})'}); r['outline'].extend(f'`{f.strip()}`' for f in files)
        r['outline'].append({'heading': f'Options ({len(opts)})'}); r['outline'].extend(f'{k} = {v.strip()}' for k, v in opts)
        r['summary'] = (f"Synplify project for {od.get('technology', '?')} {od.get('part', '')}".rstrip() +
                        f' with {len(files)} source files and {len(opts)} options.')
    elif re.search(r'^\[[^\]]+\]', text, re.M):
        secs = _ini(text)
        flat = {k: v for s in secs.values() for k, v in s}
        if 'DeviceString' in flat or '[Compiler Options]' in text[:200]:
            r['type'] = 'ImageCraft ICC IDE project (.prj, INI) — microcontroller C compiler, not FPGA'
            dev = flat.get('DeviceString', '')
            paths = [v.strip('"') for k, v in flat.items() if re.match(r'Edit\d+$', k) and re.search(r'^"?[A-Za-z]:\\|^"?\.\.?[\\/]', v)]
            fl = [v for s, kv in secs.items() if 'file' in s.lower() for _, v in kv]
            r['meta'] += [('Target device', dev)] if dev else []
            r['summary'] = (f'ImageCraft ICC compiler IDE project' + (f' for {dev}' if dev else '') +
                            (f"; include/lib/output paths {', '.join(paths[:4])}" if paths else '') +
                            (f'; {len(fl)} files' if fl else '') + '.')
            r['keywords'] = [dev] if dev else []
        else:
            r['type'] = 'Project file (INI format)'
            r['summary'] = f"INI-style project file with sections {', '.join(list(secs)[:10])}."
        for s, kv in secs.items():
            r['outline'].append({'heading': f'[{s}] ({len(kv)} keys)'})
            r['outline'].extend(f'{k} = {v}' for k, v in kv[:300] if v)
    else:
        r['type'] = 'Project file (.prj)'
    r['paragraphs'], t2 = text_pars(text)
    r['notes'] = _cap_note(t2 or trunc)
    return r


def ex_xst(path, ext):
    text, trunc = _read(path)
    opts = []
    for ln in text.split('\n'):
        if not ln.strip().startswith('-'):
            continue
        w = tcl_words(ln.strip())
        i = 0
        while i < len(w):
            if w[i].startswith('-') and len(w[i]) > 1:
                v = w[i + 1] if i + 1 < len(w) and not re.match(r'^-[a-z_]', w[i + 1]) else ''
                opts.append((w[i][1:], v)); i += 2 if v else 1
            else:
                i += 1
    od = dict(opts)
    r = {'kind': 'data', 'type': 'Xilinx XST synthesis script (.xst)', 'outline': [], 'meta': []}
    for lab, k in (('Input project', 'ifn'), ('Output', 'ofn'), ('Format', 'ofmt'), ('Part', 'p'), ('Top module', 'top'),
                   ('Optimisation', 'opt_mode')):
        if od.get(k):
            r['meta'].append((lab, od[k]))
    sets = re.findall(r'^\s*set\s+-(\S+)\s+(.*)$', text, re.M)
    r['outline'].append({'heading': f'XST options ({len(opts)})'}); r['outline'].extend(f'-{k} {v}'.strip() for k, v in opts)
    if sets:
        r['outline'].append({'heading': 'Settings'}); r['outline'].extend(f'-{k} {v}' for k, v in sets)
    r['summary'] = (f"XST synthesis script for top module {od.get('top', '?')} on {od.get('p', '?')}, reading {od.get('ifn', '?')} " +
                    (f"and writing {od['ofn']}.{od.get('ofmt', 'ngc').lower()}" if od.get('ofn') else '') + f" ({len(opts)} options).").replace('  ', ' ')
    r['keywords'] = [x for x in (od.get('top'), od.get('p')) if x]
    r['paragraphs'], _ = text_pars(text)
    return r


def ex_spl(path, ext):
    text, _ = _read(path)
    secs, cur = collections.OrderedDict(), None
    for ln in text.split('\n'):
        s = ln.strip()
        m = re.match(r'^\[(.+)\]$', s)
        if m:
            cur = m.group(1); secs.setdefault(cur, []); continue
        if s and cur:
            secs[cur].append(s)
    stem = os.path.splitext(os.path.basename(path))[0]
    dmap = {'inputs': 'input', 'outputs': 'output', 'bidirs': 'bidir', 'inouts': 'inout', 'bidirectionals': 'bidir'}
    ports = [(p, dmap.get(s.lower(), s), '') for s, ps in secs.items() for p in ps]
    r = {'kind': 'source', 'type': 'Xilinx ISE schematic symbol port list (.spl)',
         'functions': [{'name': stem, 'kind': 'symbol port list', 'params': ports,
                        'doc': ', '.join(f'{len(v)} {k.lower()}' for k, v in secs.items())}],
         'summary': f"Port list for symbol/module `{stem}`: " + '; '.join(f"{k}: {', '.join(v[:25])}" + (' …' if len(v) > 25 else '')
                                                                       for k, v in secs.items() if v) + '.',
         'keywords': [stem]}
    r['paragraphs'], _ = text_pars(text)
    return r


def ex_tfi(path, ext):
    text, _ = _read(path)
    m = re.search(r'^\s*(\w+)\s+(?:#\s*\(.*?\)\s*)?(\w+)\s*\((.*?)\);', _strip_c(text), re.S | re.M)
    r = {'kind': 'source', 'type': 'Xilinx ISE instantiation template (.tfi, Verilog)', 'code_lang': 'verilog'}
    if m:
        mod = m.group(1)
        conns = re.findall(r'\.(\w+)\s*\(\s*([^)]*)\)', m.group(3))
        r['functions'] = [{'name': mod, 'kind': 'module instantiation template', 'signature': m.group(0).strip()[:4000],
                           'params': [(a, '', f'connected to {b.strip()}') for a, b in conns],
                           'doc': f'Template for instantiating module `{mod}` with {len(conns)} ports.'}]
        r['summary'] = f'Verilog instantiation template for module `{mod}` ({len(conns)} ports: ' + ', '.join(a for a, _ in conns[:20]) + ').'
        r['keywords'] = [mod]
    r['paragraphs'], _ = text_pars(text)
    return r


def _strip_c(t):
    return re.sub(r'//[^\n]*|/\*.*?\*/', lambda m: re.sub(r'[^\n]', ' ', m.group(0)), t, flags=re.S)

# ======================================================================== memory init / waveforms

def ex_mif(path, ext):
    text, trunc = _read(path, 60_000_000)
    if '<MIFFile' in text[:200]:
        r = {'kind': 'document', 'type': 'Adobe FrameMaker Interchange Format (MIF)'}
        r['paragraphs'], t2 = text_pars(text); r['notes'] = _cap_note(t2)
        return r
    clean = re.sub(r'--[^\n]*|%[^%]*%', ' ', text)
    hdr = dict((k.upper(), v.strip()) for k, v in re.findall(r'\b(WIDTH|DEPTH|ADDRESS_RADIX|DATA_RADIX)\s*=\s*([^;]+);', clean, re.I))
    cm = re.search(r'CONTENT\s+BEGIN(.*?)(?:\bEND\b|$)', clean, re.S | re.I)
    entries = re.findall(r'([\[\]\w\.]+)\s*:\s*([^;]+);', cm.group(1)) if cm else []
    r = {'kind': 'data', 'type': 'Altera Memory Initialization File (.mif)', 'meta': [], 'outline': []}
    for k in ('WIDTH', 'DEPTH', 'ADDRESS_RADIX', 'DATA_RADIX'):
        if k in hdr:
            r['meta'].append((k.replace('_', ' ').title(), hdr[k]))
    r['meta'].append(('Content entries', len(entries)))
    comments = [c.strip(' -') for c in re.findall(r'--([^\n]*)', text[:3000]) if c.strip(' -')]
    w, d = hdr.get('WIDTH', '?'), hdr.get('DEPTH', '?')
    try:
        bits = f' ({int(w) * int(d):,} bits)'
    except Exception:
        bits = ''
    r['summary'] = (f'Memory initialisation table {d} words × {w} bits{bits}, address radix {hdr.get("ADDRESS_RADIX", "?")}, '
                    f'data radix {hdr.get("DATA_RADIX", "?")}, {len(entries)} content lines.' +
                    (' ' + ' '.join(comments[:2]) if comments else ''))
    ci = re.search(r'CONTENT\s+BEGIN', text, re.I)
    pre = text[:ci.start()] if ci else text[:4000]
    pars, _ = text_pars(pre.strip())
    n = 256
    if entries:
        pars.append({'heading': f'Content (first {min(n, len(entries))} of {len(entries)} entries)'})
        rows = [f'{a} : {v.strip()}' for a, v in entries[:n]]
        pars += ['\n'.join(rows[i:i + 32]) for i in range(0, len(rows), 32)]
    r['paragraphs'] = pars
    if len(entries) > n:
        r['notes'] = [f'Content table capped at {n} of {len(entries)} entries.']
    return r


def ex_coe(path, ext):
    text, trunc = _read(path, 60_000_000)
    clean = re.sub(r';[^\n]*?(?=\n)', lambda m: m.group(0) if '=' in m.group(0) else '', text)
    rad = re.search(r'(MEMORY_INITIALIZATION_RADIX|RADIX)\s*=\s*(\d+)', text, re.I)
    vm = re.search(r'(MEMORY_INITIALIZATION_VECTOR|COEFDATA)\s*=\s*(.*?)(?:;|$)', text, re.I | re.S)
    vals = [v for v in re.split(r'[,\s]+', vm.group(2)) if v] if vm else []
    keys = re.findall(r'^\s*(\w+)\s*=\s*([^;\n]*)', text, re.M)
    r = {'kind': 'data', 'type': 'Xilinx coefficient / memory init file (.coe)',
         'meta': [(k, v) for k, v in keys if k.upper() not in ('MEMORY_INITIALIZATION_VECTOR', 'COEFDATA')] + [('Values', len(vals))]}
    width = max((len(v) for v in vals[:2000]), default=0)
    r['summary'] = (f'Xilinx COE memory/coefficient initialisation: {len(vals)} values, radix {rad.group(2) if rad else "?"}'
                    + (f', {width} digits wide' if width else '') + '.')
    comments = [l.strip(' ;') for l in text.split('\n')[:20] if l.strip().startswith(';') and l.strip(' ;')]
    pars = comments[:]
    pars += [f'{k} = {v}' for k, v in keys if k.upper() not in ('MEMORY_INITIALIZATION_VECTOR', 'COEFDATA')]
    n = 256
    if vals:
        pars.append({'heading': f'Values (first {min(n, len(vals))} of {len(vals)})'})
        pars += [', '.join(vals[i:i + 16]) for i in range(0, min(n, len(vals)), 16)]
    r['paragraphs'] = pars
    if len(vals) > n:
        r['notes'] = [f'Value list capped at {n} of {len(vals)}.']
    return r


def _vwf_dur(block):
    """Duration of a TRANSITION_LIST body (handles nested NODE/REPEAT)."""
    pos = 0
    tok = re.compile(r'NODE\s*\{|\}|REPEAT\s*=\s*(\d+)\s*;|LEVEL\s+\S+\s+FOR\s+([\d\.eE+\-]+)\s*;')

    def node(i):
        rep, tot = 1, 0.0
        while True:
            m = tok.search(block, i)
            if not m:
                return rep * tot, len(block)
            g = m.group(0)
            if g.startswith('NODE'):
                d, i = node(m.end()); tot += d
            elif g == '}':
                return rep * tot, m.end()
            elif m.group(1):
                rep = int(m.group(1)); i = m.end()
            else:
                tot += float(m.group(2)); i = m.end()
    try:
        d, _ = node(pos)
        return d
    except Exception:
        return 0.0


def ex_vwf(path, ext):
    with open(path, 'rb') as f:
        head = f.read(4)
    if head[:3] == b'SCF' or ext == 'scf' and core.looks_binary(path):
        with open(path, 'rb') as f:
            return _gdf_like(path, 'scf', f.read(30_000_000))
    text, trunc = _read(path, 60_000_000)
    hm = re.search(r'\bHEADER\s*\{(.*?)\}', text, re.S)
    hdr = dict(re.findall(r'(\w+)\s*=\s*([^;]+);', hm.group(1))) if hm else {}
    sigs = []
    for m in re.finditer(r'\bSIGNAL\s*\(\s*"([^"]+)"\s*\)\s*\{(.*?)\}', text, re.S):
        kv = dict(re.findall(r'(\w+)\s*=\s*([^;]+);', m.group(2)))
        sigs.append((m.group(1), kv.get('DIRECTION', ''), kv.get('WIDTH', ''), kv.get('PARENT', '').strip('"')))
    tl = re.search(r'TRANSITION_LIST\s*\(\s*"[^"]*"\s*\)\s*\{', text)
    end = 0.0
    if tl:
        e = _brace_end(text, tl.end() - 1)
        end = _vwf_dur(text[tl.end():e + 1])
    unit = hdr.get('TIME_UNIT', 'ns').strip()
    r = {'kind': 'data', 'type': 'Quartus vector waveform file (.vwf)' if ext == 'vwf' else 'Waveform / simulation file',
         'meta': [(k.replace('_', ' ').title(), v.strip()) for k, v in hdr.items()], 'outline': []}
    if end:
        r['meta'].append(('Waveform end time', f'{end:g} {unit}'))
    top = [s for s in sigs if not s[3]]
    r['outline'].append({'heading': f'Signals ({len(sigs)})'})
    r['outline'].extend(f'`{n}` {d.lower()}' + (f' [{w} bits]' if w and w.strip() not in ('1',) else '') + (f' (in {p})' if p else '')
                        for n, d, w, p in sigs[:MAX_OUTLINE * 2])
    cnt = collections.Counter(d for _, d, _, _ in top)
    r['summary'] = (f"Simulation waveform with {len(top)} top-level signals ({', '.join(f'{v} {k.lower()}' for k, v in cnt.items())}"
                    f"){f'; vectors run to {end:g} {unit}' if end else ''}: " + ', '.join(n for n, _, _, _ in top[:25]) +
                    (' …' if len(top) > 25 else '') + '.')
    r['keywords'] = [n for n, _, _, _ in top[:6]]
    # paragraphs: header + signal declarations, skip bulky transition data
    body = strip_license(text)
    body = re.sub(r'TRANSITION_LIST\s*\(\s*"([^"]+)"\s*\)\s*\{', r'TRANSITION_LIST("\1") {', body)
    cut = body.find('TRANSITION_LIST(')
    pars, t2 = text_pars(body[:cut] if cut > 0 else body)
    rest = body[cut:] if cut > 0 else ''
    tail = re.split(r'\n(?=DISPLAY_LINE|TIME_BAR|;)', rest, 1)
    if len(tail) > 1:
        p2, _ = text_pars(tail[1], cap=1500)
        pars += [{'heading': 'Display settings'}] + p2
    r['paragraphs'] = pars
    r['notes'] = ['Waveform transition data (TRANSITION_LIST blocks) omitted from full text.'] if cut > 0 else []
    return r

# ======================================================================== MAX+PLUS II text files

def ex_acf(path, ext):
    text, trunc = _read(path)
    clean = re.sub(r'--[^\n]*', '', text)
    chips = [c.strip('"') for c in re.findall(r'\bCHIP\s+(\S+)', clean)]
    devs = [d.strip().strip('"') for d in re.findall(r'\bDEVICE\s*=\s*([^;]+);', clean)]
    pins = re.findall(r'^\s*"?\|?([^":\n]+?)"?\s*:\s*(INPUT_PIN|OUTPUT_PIN|BIDIR_PIN|PIN|LOCATION)\s*=\s*([^;]+);', clean, re.M)
    secs = re.findall(r'^\s*([A-Z_]+)\s*$\s*BEGIN', clean, re.M)
    ver = re.search(r'Version\s+([\d\.]+[^\n]*)', text[:1500])
    names = {'acf': 'MAX+PLUS II Assignment & Configuration File (.acf)', 'fit': 'MAX+PLUS II compiler fit file (.fit)',
             'hif': 'MAX+PLUS II / Quartus hierarchy interconnect file (.hif)', 'cdf': 'Quartus JTAG chain description (.cdf)'}
    r = {'kind': 'data', 'type': names.get(ext, 'Altera file'), 'outline': [], 'meta': []}
    if ver:
        r['meta'].append(('Tool version', ver.group(1).strip()))
    comp = re.search(r'Compiled:\s*([^\n]+)', text[:1500])
    if comp:
        r['meta'].append(('Compiled', comp.group(1).strip()))
    if chips:
        r['meta'].append(('Chip', ', '.join(chips[:5])))
    if devs:
        r['meta'].append(('Device', ', '.join(d.strip() for d in devs[:5])))
    io = [(a.strip(), b, c.strip()) for a, b, c in pins if b != 'LOCATION']
    lc = [(a.strip(), b, c.strip()) for a, b, c in pins if b == 'LOCATION']
    if io:
        r['outline'].append({'heading': f'Pin assignments ({len(io)})'})
        r['outline'].extend(f'pin {c} -> `{a}` ({b.replace("_PIN", "").lower() or "pin"})' for a, b, c in io[:MAX_OUTLINE])
    if lc:
        r['outline'].append({'heading': f'Logic-cell locations ({len(lc)})'})
        r['outline'].extend(f'{c} -> `{a}`' for a, b, c in lc[:MAX_OUTLINE])
    if secs:
        r['outline'].append({'heading': 'Sections'}); r['outline'].extend(sorted(set(secs)))
    if ext == 'cdf':
        parts = re.findall(r'PartName\(([^)]+)\)', text)
        files = re.findall(r'File\("([^"]*)"\)', text)
        acts = re.findall(r'ActionCode\(([^)]+)\)', text)
        qv = re.search(r'Quartus II[^\n*]*', text[:300])
        r['meta'] += [('Quartus', qv.group(0).strip())] if qv else []
        r['outline'].append({'heading': 'JTAG chain'})
        r['outline'].extend(f'{i + 1}. {p}' + (f' — file `{files[i]}`' if i < len(files) else '') +
                            (f' — action {acts[i]}' if i < len(acts) else '') for i, p in enumerate(parts))
        r['summary'] = (f"Quartus programmer chain with {len(parts)} device(s): {', '.join(parts)}" +
                        (f"; programming files {', '.join(f for f in files if f)}" if any(files) else '') + '.')
        r['keywords'] = parts + [f for f in files if f][:4]
    elif ext == 'hif':
        files = re.findall(r'^\t([^\s{}]+\.\w+)\s*$', text, re.M)
        ents = re.findall(r'^\t\t(\S+)\s+\[([^\]]*)\]', text, re.M)
        insts = len(re.findall(r'^\t\t\t\S+\s+\[', text, re.M))
        r['outline'].append({'heading': f'Design files in hierarchy ({len(files)})'})
        r['outline'].extend(f'`{f}`' for f in files[:MAX_OUTLINE])
        if ents:
            r['outline'].append({'heading': 'Entities and their parameters'})
            r['outline'].extend(f'`{e}`' + (f' [{p[:200]}]' if p else '') for e, p in ents[:MAX_OUTLINE])
        hv = text.strip().split('\n', 1)[0].strip()
        r['meta'].append(('Format', hv))
        r['summary'] = (f'Altera hierarchy interconnect file ({hv}) describing {len(files)} design files / {len(ents)} entities '
                        f'and {insts} instance parameterisations: ' + ', '.join(files[:15]) + '.')
        r['keywords'] = [os.path.splitext(f)[0] for f in files if not re.match(r'(lpm_|alt|a_|db/)', f)][:6]
    else:
        r['summary'] = (r['type'].split(' (')[0] + (f" for chip {chips[0]}" if chips else '') +
                        (f" on {devs[0].strip()}" if devs else '') +
                        (f' with {len(io)} pin assignments' if io else '') +
                        (f' and {len(lc)} logic-cell placements' if lc else '') + '.')
        r['keywords'] = [d.strip() for d in devs[:2]] + chips[:2]
    r['paragraphs'], t2 = text_pars(text)
    r['notes'] = _cap_note(t2 or trunc)
    return r

# ======================================================================== ModelSim / ChipScope / misc INI

def ex_mpf(path, ext):
    text, _ = _read(path)
    secs = _ini(text)
    r = {'kind': 'data', 'type': 'ModelSim project file (.mpf)', 'outline': [], 'meta': []}
    proj = dict(secs.get('Project', []))
    files = [v for k, v in proj.items() if re.match(r'Project_File_\d+$', k)]
    libs = [k for k, v in secs.get('Library', [])]
    r['meta'] += [('Project files', len(files)), ('Library mappings', len(libs))]
    if proj.get('Project_Version'):
        r['meta'].append(('Project version', proj['Project_Version']))
    if files:
        r['outline'].append({'heading': f'Project sources ({len(files)})'}); r['outline'].extend(f'`{f}`' for f in files)
    for s, kv in secs.items():
        r['outline'].append({'heading': f'[{s}] ({len(kv)} entries)'})
        r['outline'].extend(f'{k} = {v}' for k, v in kv[:200])
    r['summary'] = (f'ModelSim project/initialisation file with {len(libs)} library mappings' +
                    (f' and {len(files)} project source files ({", ".join(os.path.basename(f) for f in files[:8])})' if files else '') + '.')
    r['paragraphs'], t2 = text_pars(text)
    r['notes'] = _cap_note(t2)
    return r


def ex_mti(path, ext):
    text, _ = _read(path)
    files = re.findall(r'\{([^{}]+\.(?:vhd|vhdl|v|sv))\}', text, re.I)
    ents = re.findall(r'--\s*Compiling\s+(entity|architecture|module|package)\s+(\S+)(?:\s+of\s+(\S+))?', text)
    tool = re.search(r'Model Technology[^\n]*', text)
    r = {'kind': 'data', 'type': 'ModelSim compile record (.mti)', 'meta': [('Tool', tool.group(0).strip())] if tool else [],
         'outline': [{'heading': f'Compiled files ({len(set(files))})'}] + [f'`{f}`' for f in dict.fromkeys(files)] +
                    [{'heading': 'Design units'}] + [f'{a} {b}' + (f' of {c}' if c else '') for a, b, c in ents]}
    r['summary'] = (f'ModelSim compile history for {len(set(files))} source files; design units: ' +
                    ', '.join(dict.fromkeys(b for a, b, _ in ents if a in ('entity', 'module')))[:400] + '.')
    r['keywords'] = list(dict.fromkeys(b for a, b, _ in ents if a in ('entity', 'module')))[:6]
    r['paragraphs'], _ = text_pars(text)
    return r


def ex_props(path, ext):
    text, _ = _read(path)
    kv = re.findall(r'^\s*([^#=\s][^=\n]*?)\s*=\s*(.*)$', text, re.M)
    d = dict(kv)
    r = {'kind': 'data', 'type': 'Xilinx ChipScope Pro Analyzer project (.cpj)', 'outline': [], 'meta': []}
    devs = [v for k, v in kv if re.match(r'deviceChain\.deviceName\d+', k)]
    hdr = re.search(r'#(ChipScope[^\n]*)', text)
    if hdr:
        r['meta'].append(('Format', hdr.group(1).strip()))
    r['meta'].append(('Properties', len(kv)))
    if devs:
        r['outline'].append({'heading': 'JTAG device chain'}); r['outline'].extend(devs)
    sigs = [v for k, v in kv if re.search(r'signal|\.name$', k, re.I)][:300]
    if sigs:
        r['outline'].append({'heading': f'Signal / unit names ({len(sigs)})'}); r['outline'].extend(f'`{s}`' for s in sigs)
    bit = [v for k, v in kv if k.endswith('configFilename') and v]
    r['summary'] = (f"ChipScope Pro analyzer project for JTAG chain {', '.join(devs) or '?'}" +
                    (f", bitstream {', '.join(bit)}" if bit else '') + f' ({len(kv)} saved settings).')
    r['keywords'] = devs[:4]
    r['paragraphs'], _ = text_pars(text)
    return r

# ======================================================================== Gerber / P-CAD reports (share extensions)

GERBER_LAYER = {'bsm': 'bottom solder mask', 'tsm': 'top solder mask', 'bss': 'bottom silkscreen',
                'tss': 'top silkscreen', 'bst': 'bottom solder paste (stencil)', 'tst': 'top solder paste'}


def ex_gerber(path, ext):
    text, _ = _read(path, 30_000_000)
    if text.count('\n') < text.count('*') / 20:
        text = text.replace('*', '*\n')
    g04 = [l.strip()[3:].strip(' *')[:200] for l in text.split('\n') if l.strip().startswith('G04')][:400]
    info = {}
    for l in g04:
        m = re.match(r'(File|Source|Format|File Contents|Format Options|File Options):\s*(.*)', l)
        if m:
            info[m.group(1)] = m.group(2)
    ad = re.findall(r'%ADD(\d+)([^*%]*)', text)
    am = re.findall(r'%AM(\w+)', text)
    dcodes = re.findall(r'D(\d{2,3})\*', text)
    contents = []
    capture = False
    for l in g04:
        if l.startswith('File Contents:'):
            capture = True; contents.append(l.split(':', 1)[1].strip()); continue
        if capture:
            if not l or ':' in l:
                break
            contents.append(l)
    layer = GERBER_LAYER.get(ext, '')
    yes = [c for c in contents if not c.lower().startswith('no ')]
    r = {'kind': 'data', 'type': f'Gerber photoplot (RS-274) — PCB {layer}' if layer else
         'Gerber aperture macro library (.apr_lib)', 'meta': [(k, v) for k, v in info.items()],
         'outline': [{'heading': 'Header comments'}] + [x for x in g04 if x][:200]}
    r['meta'] += [('Aperture definitions', len(ad) or len(am)), ('Aperture macros', len(am)), ('Plot commands', text.count('*'))]
    src = info.get('Source', '')
    if layer:
        r['summary'] = (f"Gerber artwork for the PCB {layer} layer" + (f" ({', '.join(yes)})" if yes else '') +
                        (f", produced by {src}" if src else '') + '. This is a PCB manufacturing file, not an FPGA file.')
    else:
        dc = ', '.join(sorted(set(re.findall(r'DCode=(\d+)', text)), key=int)[:15])
        r['summary'] = f'Altium/PCB Gerber aperture macro library with {len(am)} aperture macros (D-codes {dc} ...). PCB file, not FPGA.'
    pars = ['\n'.join(g04[:80])] if g04 else []
    r['paragraphs'] = pars
    r['notes'] = ['Gerber coordinate data not reproduced (vector plot commands only).']
    r['keywords'] = [os.path.basename(src.split(',')[-1].strip(' ()'))] if src else []
    return r


def ex_report(path, ext):
    text, trunc = _read(path)
    first = next((l.strip() for l in text.split('\n') if l.strip()), '')
    r = {'kind': 'document', 'meta': [], 'outline': []}
    if ext == 'sta':
        r['type'] = 'P-CAD / ACCEL PCB board statistics report (.sta)'
        stats = re.findall(r'([A-Z][A-Za-z ]+?):\s+([\d\.]+)', text)
        r['meta'] += stats[:40]
        r['summary'] = f'{first.split("  ")[0]} for {first.split()[-1]}: ' + ', '.join(f'{k} {v}' for k, v in stats[:10]) + '. PCB report, not FPGA.'
    elif ext == 'apr':
        r['type'] = 'P-CAD aperture definitions & assignments report (.apr)'
        dc = re.findall(r'^\s*(D\d+)\s+(\S+)\s+([\d\.]+)\s+([\d\.]+)', text, re.M)
        r['outline'] = [{'heading': f'Apertures ({len(dc)})'}] + [f'{a} {b} {c}×{d}' for a, b, c, d in dc[:400]]
        hd = first.split('  ')[0] if 'Aperture' in first else 'Aperture list'
        board = first.split()[-1] if 'Aperture' in first else ''
        r['summary'] = f'{hd}' + (f' for {board}' if board else '') + f': {len(dc)} aperture definitions (Gerber D-codes). PCB report, not FPGA.'
    else:
        r['type'] = 'Report / listing'
    r['paragraphs'], t2 = text_pars(text)
    r['notes'] = _cap_note(t2 or trunc)
    return r


def ex_rlf(path, ext):
    with open(path, 'rb') as f:
        data = f.read(30_000_000)
    i = data.find(b'\n')
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', data.decode('latin-1')).replace('\r', '')
    r = {'kind': 'document', 'type': 'Microchip MPLAB XC8/HI-TECH relocatable listing (.rlf) — PIC firmware build output, not FPGA',
         'meta': []}
    m = re.search(r'processor\s+(\S+)', text)
    asm = re.search(r'(Microchip[^\n]*Assembler[^\n]*)', text)
    if m:
        r['meta'].append(('Processor', m.group(1)))
    if asm:
        r['meta'].append(('Tool', asm.group(1).strip()))
    r['summary'] = (f'Assembler relocatable listing' + (f' for PIC {m.group(1)}' if m else '') +
                    (f' produced by {asm.group(1).strip()}' if asm else '') + '.')
    r['paragraphs'], t2 = text_pars(text, lic=False)
    r['notes'] = _cap_note(t2) + ['Binary record framing stripped; text portions shown.']
    return r


def name_is_qsf(nm):
    return nm.lower().endswith(b'.qsf')


def ex_qar(path, ext):
    with open(path, 'rb') as f:
        data = f.read(200_000_000)
    t0 = time.time()
    entries, qsf = [], None
    last = 0
    mv = memoryview(data)
    for m in re.finditer(rb'x[\x01\x5e\x9c\xda]', data):
        p = m.start()
        if p < last:
            continue
        for L in range(1, 256):
            if p - L - 2 < 0:
                break
            if data[p - L - 2] == L and data[p - L - 1] == 0:
                nm = data[p - L:p]
                if all(32 <= c < 127 for c in nm) and re.search(rb'\.\w+$', nm):
                    try:
                        o = zlib.decompressobj()
                        q, size, keep, CH = p, 0, [], 1 << 20
                        while not o.eof and q < len(data):
                            chunk = o.decompress(mv[q:q + CH])
                            size += len(chunk)
                            if name_is_qsf(nm) and size < 20_000_000:
                                keep.append(chunk)
                            q += CH
                        out = b''.join(keep)
                        name = nm.decode()
                        entries.append((name, size))
                        last = min(q, len(data)) - len(o.unused_data)
                        if qsf is None and name.lower().endswith('.qsf'):
                            qsf = (name, out.decode('latin-1'))
                        del out
                    except Exception:
                        pass
                break
        if time.time() - t0 > 25:
            break
    r = {'kind': 'binary', 'type': 'Quartus II project archive (.qar)', 'outline': [], 'meta': [('Archived files', len(entries))]}
    if entries:
        exts = collections.Counter(os.path.splitext(n)[1].lower() or '(none)' for n, _ in entries)
        r['outline'].append({'heading': f'Archive contents ({len(entries)})'})
        r['outline'].extend(f'`{n}` ({s:,} bytes)' for n, s in entries[:MAX_OUTLINE * 2])
        r['summary'] = (f'Quartus II project archive containing {len(entries)} files ({sum(s for _, s in entries):,} bytes uncompressed; '
                        + ', '.join(f'{v} {k}' for k, v in exts.most_common(8)) + ').')
    else:
        r['summary'] = 'Quartus II project archive (compressed); no entries could be decoded.'
    if qsf:
        q = quartus_parse(qsf[1])
        tmp = {}
        s = quartus_report(q, tmp, 'Project settings')
        r['summary'] += f' Embedded {qsf[0]}: {s}'
        r['meta'] += tmp.get('meta', [])
        r['keywords'] = tmp.get('keywords', [])
        r['outline'] += [{'heading': f'From embedded {qsf[0]}'}] + tmp.get('outline', [])[:800]
        r['paragraphs'], _ = text_pars(qsf[1], cap=2000)
        r['paragraphs'].insert(0, {'heading': f'Embedded {qsf[0]}'})
    return r


def ex_binary_strings(path, ext):
    with open(path, 'rb') as f:
        data = f.read(30_000_000)
    names = {'ise': 'Xilinx ISE 8–11 project repository (.ise, binary)', 'ipf': 'Xilinx iMPACT project file (.ipf, binary)',
             'xaw': 'Xilinx Architecture Wizard clocking settings (.xaw, encoded XDB)',
             'qpw': 'Quattro Pro for Windows spreadsheet (.qpw, binary) — not an FPGA file',
             'qws': 'Quartus II workspace settings (.qws, binary)'}
    r = {'kind': 'binary', 'type': names.get(ext, 'Binary file')}
    st = _strings(data, 4, 4000)
    if ext == 'xaw':
        st = [s for s in st if s.startswith('XILINX') or re.match(r'^[A-Za-z_][\w \.\-]{3,40}$', s)][:20]
    vers = re.findall(rb'ISE_VERSION_\w+\s*\n?\s*([\d\.]+)', data)
    files = sorted({s for s in st if re.search(r'\.(v|vhd|ucf|bit|mcs|xco|ngc|sch|tdf|bdf|mcs|prom|cdf|xise|jed)\b', s, re.I) and len(s) < 200})
    r['meta'] = [('ISE version', vers[0].decode())] if vers else []
    if files:
        r['outline'] = [{'heading': f'Referenced files ({len(files)})'}] + [f'`{x}`' for x in files[:400]]
    r['summary'] = r['type'] + (f' (ISE {vers[0].decode()})' if vers else '') + (
        f"; references {len(files)} files, e.g. {', '.join(files[:6])}" if files else '') + '.'
    r['paragraphs'] = [' · '.join(st[i:i + 30]) for i in range(0, min(len(st), 1500), 30)]
    r['notes'] = ['Binary format: only embedded printable strings were extracted.']
    return r


def ex_pin(path, ext):
    text, trunc = _read(path)
    rows = re.findall(r'^\s*(\S+)\s*:\s*(\S+)\s*:\s*(input|output|bidir|gnd|power|\w*)\s*:\s*([^:\n]*):', text, re.M)
    r = {'kind': 'data', 'type': 'Quartus pin-out report (.pin)',
         'outline': [{'heading': f'Pins ({len(rows)})'}] + [f'{b} -> `{a}` {c} {d.strip()}' for a, b, c, d in rows
                                                             if a not in ('GND', 'VCCIO', 'VCCINT', 'RESERVED_INPUT', 'NC')][:2000]}
    dev = re.search(r'CHIP\s+"([^"]+)"\s+ASSIGNED TO AN:\s*(\S+)', text)
    r['summary'] = (f'Quartus pin-out report' + (f' for {dev.group(1)} on {dev.group(2)}' if dev else '') + f' ({len(rows)} pins).')
    r['paragraphs'], t2 = text_pars(text)
    r['notes'] = _cap_note(t2)
    return r

# ======================================================================== dispatch

DISPATCH = {
    'qsf': ex_qsf, 'qsf~': ex_qsf, 'qip': ex_qsf, 'qdf': ex_qsf, 'qpf': ex_qpf,
    'sdc': ex_sdc, 'sdc~': ex_sdc, 'xdc': ex_sdc,
    'tcl': ex_tcl, 'tcl~': ex_tcl, 'do': ex_tcl,
    'ucf': ex_ucf, 'ncf': ex_ucf, 'pcf': ex_ucf, 'lpf': ex_ucf, 'pdc': ex_ucf,
    'bsf': ex_bdf, 'bdf': ex_bdf, 'gdf': ex_bdf,
    'tdf': ex_tdf,
    'xco': ex_xco, 'cgp': ex_xco,
    'xise': ex_xml, 'gise': ex_xml, 'ppf': ex_xml, 'jdi': ex_xml, 'cgc': ex_xml,
    'prj': ex_prj, 'xst': ex_xst, 'spl': ex_spl, 'tfi': ex_tfi,
    'mif': ex_mif, 'coe': ex_coe, 'vwf': ex_vwf, 'scf': ex_vwf,
    'acf': ex_acf, 'fit': ex_acf, 'hif': ex_acf, 'cdf': ex_acf,
    'mpf': ex_mpf, 'mti': ex_mti, 'cpj': ex_props,
    'bsm': ex_gerber, 'bss': ex_gerber, 'bst': ex_gerber, 'tsm': ex_gerber, 'tss': ex_gerber, 'apr_lib': ex_gerber,
    'apr': ex_report, 'sta': ex_report, 'rlf': ex_rlf, 'qar': ex_qar,
    'ise': ex_binary_strings, 'ipf': ex_binary_strings, 'xaw': ex_binary_strings, 'qpw': ex_binary_strings,
    'qws': ex_binary_strings, 'pin': ex_pin,
}


def _fallback(path, err=None):
    try:
        if core.looks_binary(path):
            with open(path, 'rb') as f:
                st = _strings(f.read(10_000_000), 4, 1500)
            r = {'kind': 'binary', 'paragraphs': [' · '.join(st[i:i + 30]) for i in range(0, len(st), 30)],
                 'notes': ['Binary file: embedded strings only.']}
        else:
            text, _ = _read(path)
            pars, t = text_pars(text)
            r = {'kind': 'document', 'paragraphs': pars, 'notes': _cap_note(t)}
    except Exception:
        r = {'kind': 'binary'}
    if err:
        r.setdefault('notes', []).append(f'Specialised parse failed ({err}); plain text shown.')
    return r


def extract(path):
    name = os.path.basename(path).lower()
    ext = name.rsplit('.', 1)[1] if '.' in name else ''
    fn = DISPATCH.get(ext)
    if fn is None:
        return _fallback(path)
    try:
        if os.path.getsize(path) == 0:
            return {'kind': 'data', 'type': f'Empty .{ext} file', 'notes': ['File is empty (0 bytes).'],
                    'summary': f'Empty .{ext} file.'}
        r = fn(path, ext)
        r = {k: v for k, v in r.items() if v not in (None, '', [])}
        if r.get('type'):
            r['type'] = re.sub(r'\s*\(\.%s\)' % re.escape(ext.rstrip('~')), '', r['type'])
        return r
    except Exception as e:
        return _fallback(path, f'{type(e).__name__}: {str(e)[:100]}')
