"""VHDL extractor: entities, architectures, processes, functions/procedures,
components, packages; libraries, signals, constants, types, instances.

Also handles tool-generated VHDL (Altera MegaWizard / IP Toolbench, Quartus
.cmp component files, Xilinx CORE Generator .vho templates, sch2hdl .vhf and
netgen netlists). Non-VHDL .cmp files (Eagle/Gerber component-side plots and
anything else) are detected by content and fall back to plain text.
"""
import re, bisect, collections
import core

EXTS = {'vhd', 'vhdl', 'vho', 'vhf', 'vhd~', 'vhd#', 'vht', 'vhi', 'cmp'}

I = re.I
LEX = re.compile(r"'[^\n]'|\"[^\"\n]*\"|--[^\n]*")
DECOR = re.compile(r'^[\s\-=*#_~+/\\|.:<>]*$')
BOILER = re.compile(r'"as is"|must appear in the vhdl|comp_tag|inst_tag|compile the wrapper file|warrant|liabil|licen[cs]|copyright|all rights reserved|prohibit|disclaim|life support|'
                    r'megafunction partner|proprietary|owned and controlled by|merchantab|infring|'
                    r'subject to the terms|program license|wizard-generated file|do not edit|'
                    r'should not be modified|indemnif|confidential', I)
CODEY = re.compile(r';\s*$|<=|:=|=>|^\s*(if|elsif|else|end|when|case|begin|process|signal|variable|port|'
                   r'generic|component|entity|architecture|library|use|for|loop|wait|report|assert)\b', I)
FIELD = re.compile(r'^(Company|Engineer|Author|Create Date|Date Created|Date Last Modified|Design Name|Module Name|'
                   r'Project Name|Target Devices?|Tool [Vv]ersions?|Description|Desc|Dependencies|Revision|Rev|Date|'
                   r'Device|Vendor|Version|Application|Filename|File Name|Timestamp|Purpose|Command|Design|Title|'
                   r'Function|Notes?|Additional Comments|Megafunction Name\(s\)|MODULE|GENERATION)\s*:\s*(.*)$', I)
META_FIELDS = {'company', 'engineer', 'author', 'create date', 'date created', 'date last modified', 'project name',
               'target device', 'target devices', 'tool versions', 'tool version', 'vendor', 'version',
               'application', 'timestamp', 'device', 'design name', 'module'}
UNIT = re.compile(r'\b(?:entity\s+(\w+)\s+is\b|architecture\s+(\w+)\s+of\s+(\w+)\s+is\b|'
                  r'package\s+(body\s+)?(\w+)\s+is\b(?!\s+new\b)|configuration\s+(\w+)\s+of\s+(\w+)\s+is\b)', I)
COMP = re.compile(r'\bcomponent\s+(\w+)(?:\s+is)?\b', I)
SUBP = re.compile(r'\b(?:(pure|impure)\s+)?(function|procedure)\s+(\w+|"[^"]*")', I)
PROC = re.compile(r'\bprocess\b', I)
INST = re.compile(r'\b(\w+)\s*:\s*(?:(entity)\s+([\w\.]+)(?:\s*\(\s*(\w+)\s*\))?|(?:(component|configuration)\s+)?([\w\.]+))'
                  r'\s+(generic|port)\s+map\b', I)
SIG = re.compile(r'\bsignal\s+([\w\s,]+?)\s*:\s*([^;]+?)\s*;', I)
CONST = re.compile(r'\bconstant\s+([\w\s,]+?)\s*:\s*([^;]+?)\s*;', I)
TYPE = re.compile(r'\b(type|subtype)\s+(\w+)\s+is\s+', I)
LIB = re.compile(r'\blibrary\s+([\w\s,]+?)\s*;', I)
USE = re.compile(r'\buse\s+([\w\.\s,]+?)\s*;', I)
KEYWORDS = set('''abs access after alias all and architecture array assert attribute begin block body buffer bus case
component configuration constant disconnect downto else elsif end entity exit file for function generate generic
group guarded if impure in inertial inout is label library linkage literal loop map mod nand new next nor not null
of on open or others out package port postponed procedure process pure range record register reject rem report
return rol ror select severity signal shared sla sll sra srl subtype then to transport type unaffected units until
use variable wait when while with xnor xor'''.split())
MAX_INST = 200
MAX_SIG = 100


def ws(s):
    return re.sub(r'\s+', ' ', s).strip()


def match_paren(s, i):
    """s[i] == '(' -> index of matching ')' (or len(s))."""
    d = 0
    n = len(s)
    j = i
    while j < n:
        c = s[j]
        if c == '(':
            d += 1
        elif c == ')':
            d -= 1
            if d == 0:
                return j
        j += 1
    return n


def split_top(s, sep=';'):
    """Split on sep at paren depth 0; returns list of (offset, text)."""
    out, d, st = [], 0, 0
    for j, c in enumerate(s):
        if c == '(':
            d += 1
        elif c == ')':
            d -= 1
        elif c == sep and d == 0:
            out.append((st, s[st:j])); st = j + 1
    out.append((st, s[st:]))
    return [(o, t) for o, t in out if t.strip()]


def clean_comment(c):
    c = c[2:] if c.startswith('--') else c
    c = c.strip()
    c = re.sub(r'^[\-=*#~!]+', '', c)
    c = re.sub(r'[\-=*#~]{2,}\s*$', '', c)
    return c.strip()


class Src:
    def __init__(self, text):
        self.text = text
        self.nl = [m.start() for m in re.finditer('\n', text)]
        self.comments = {}          # line -> cleaned comment
        self.raw_comments = {}      # line -> raw comment text
        parts, last = [], 0
        for m in LEX.finditer(text):
            g = m.group(0)
            if g.startswith('--'):
                parts.append(text[last:m.start()])
                parts.append(' ' * len(g))
                last = m.end()
                ln = self.line(m.start())
                self.raw_comments[ln] = g
                self.comments[ln] = clean_comment(g)
        parts.append(text[last:])
        self.code = ''.join(parts)
        self.lines = text.split('\n')
        self.code_lines = self.code.split('\n')

    def line(self, off):
        return bisect.bisect_right(self.nl, off - 1) + 1

    def comment_only(self, ln):
        return ln in self.comments and not self.code_lines[ln - 1].strip()

    def doc_before(self, ln, also_inline=True):
        """Contiguous comment block directly above line ln (allows one blank line)."""
        out, k, blanks = [], ln - 1, 0
        while k >= 1:
            if self.comment_only(k):
                out.append(self.comments[k]); blanks = 0
            elif not self.code_lines[k - 1].strip() and not out and blanks == 0:
                blanks += 1
            else:
                break
            k -= 1
            if len(out) > 40:
                break
        out.reverse()
        txt = [l for l in out if l and not DECOR.match(l) and not CODEY.search(l)]
        doc = ' '.join(txt)
        if also_inline and ln in self.comments and self.code_lines[ln - 1].strip():
            c = self.comments[ln]
            if c and not DECOR.match(c):
                doc = (doc + ' ' + c).strip()
        if BOILER.search(doc) and len(doc) > 200:
            return ''
        return doc[:600]

    def src_slice(self, a, b, max_lines=60):
        la, lb = self.line(a), self.line(max(a, b - 1))
        lines = self.lines[la - 1:lb]
        if len(lines) > max_lines:
            more = len(lines) - max_lines
            lines = lines[:max_lines] + [f'-- ... {more} more lines']
        # de-indent
        ind = min((len(l) - len(l.lstrip()) for l in lines[1:] if l.strip()), default=0)
        out = [lines[0].strip()] + [l[ind:].rstrip() for l in lines[1:]]
        return '\n'.join(out).replace('\t', '    ')


def parse_items(src, base, body, generic=False):
    """Port / generic / parameter list body -> params rows."""
    rows = []
    for off, item in split_top(body):
        m = re.match(r'\s*(?:(signal|constant|variable|file)\s+)?([\w\s,]+?)\s*:\s*'
                     r'(?:(in|out|inout|buffer|linkage)\b)?\s*(.*)$', item, I | re.S)
        if not m:
            continue
        cls, names, mode, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        dflt = ''
        if ':=' in rest:
            rest, dflt = rest.split(':=', 1)
        typ = ws(rest)
        desc = ' '.join(x for x in [('generic' if generic else ''), (mode or '').lower(), typ] if x)
        if cls and not generic:
            desc = cls.lower() + ' ' + desc
        if dflt.strip():
            desc += ' := ' + ws(dflt)
        # inline comment(s) on the lines spanned by this item (or the line after ';')
        la = src.line(base + off + (len(item) - len(item.lstrip())))
        lb = src.line(base + off + len(item))
        notes = [src.comments.get(l, '') for l in range(la, lb + 1)]
        note = ' '.join(n for n in notes if n and not DECOR.match(n))
        for nm in re.split(r'\s*,\s*', names.strip()):
            if nm:
                rows.append((nm, desc, note[:200]))
    return rows


def header_clause(code, a, b, kw):
    m = re.compile(r'\b' + kw + r'\s*\(', I).search(code, a, b)
    if not m:
        return None
    p = code.index('(', m.start())
    q = match_paren(code, p)
    return p + 1, code[p + 1:q], q


def in_spans(spans, starts, off):
    k = bisect.bisect_right(starts, off) - 1
    return k >= 0 and spans[k][0] <= off < spans[k][1]


def detect_tool(text, name):
    head = text[:6000]
    hl = head.lower()
    facts, tool, ip = [], '', ''
    m = re.search(r'megafunction wizard:\s*%([^%]+)%', head, I)
    if m:
        ip = m.group(1).strip()
        tool = 'Altera MegaWizard'
    m2 = re.search(r'Generated by\s+(.+?)\s*\[Altera,?\s*(.*?)\]', head, I)
    if m2:
        tool = 'Altera IP Toolbench'; ip = ip or m2.group(1).strip()
        facts.append(('Generator', ws(m2.group(1) + ' / ' + m2.group(2))))
    if 'with identifier' in hl:
        cl = [clean_comment(l) for l in head.split('\n') if l.strip().startswith('--')]
        cl = [l for l in cl if l and not DECOR.match(l)]
        for i, l in enumerate(cl):
            m4 = re.search(r'with identifier:\s*(\S*)', l, I)
            if m4:
                rest = cl[i + 1:]
                ip = m4.group(1) or (rest.pop(0) if rest else '')
                if rest and not re.search(r'must appear|cut here|comp_tag', rest[0], I):
                    facts.append(('Core description', rest[0]))
                break
    m3 = re.search(r'^--\s*(\d+\.\d+[^\n]*Build[^\n]*)$', head, re.M | I)
    if m3:
        facts.append(('Quartus version', ws(m3.group(1))))
    if not tool and 'altera' in hl and name.endswith('.cmp'):
        tool = 'Altera component declaration'
    if 'application' in hl and 'netgen' in hl:
        tool = 'Xilinx netgen simulation netlist'
    elif 'sch2hdl' in hl:
        tool = 'Xilinx sch2hdl schematic netlist'
    elif 'comp_tag' in hl or 'core generator' in hl or 'coregen' in hl:
        tool = tool or 'Xilinx CORE Generator'
    elif re.search(r'quartus.*vhdl.*netlist|vhdl netlist.*quartus', hl, re.S) or ('quartus' in hl and name.endswith('.vho')):
        tool = 'Quartus VHDL output netlist'
    elif not tool:
        mm = re.search(r'^--\s*(?:this (?:file|code|netlist) (?:was|is|has been) )?(?:auto(?:matically)?[- ])?'
                       r'generated (?:by|with|using)\s+([A-Za-z][^\n]{1,60})', head[:2500], re.M | I)
        if mm:
            tool = 'Tool-generated (' + ws(re.sub(r'[\-=*#]{2,}.*$', '', mm.group(1))) + ')'
    return tool, ip, facts


def header_comments(src):
    """Comment lines before the first code token -> cleaned paragraphs + field facts."""
    first = re.search(r'\S', src.code)
    end_line = src.line(first.start()) if first else len(src.lines) + 1
    pars, cur, fields = [], [], []
    for ln in range(1, end_line):
        raw = src.comments.get(ln)
        if raw is None:
            if cur:
                pars.append(cur); cur = []
            continue
        c = re.sub(r'^[\s/\\_|]+', '', raw).strip()
        c = re.sub(r'\s*[\-=*#]{2,}$', '', c).strip()
        if not c or DECOR.match(c):
            if cur:
                pars.append(cur); cur = []
            continue
        fm = FIELD.match(c)
        if fm:
            k, v = fm.group(1).strip(), fm.group(2).strip()
            if v and not DECOR.match(v):
                fields.append((k, v))
            if k.lower() in META_FIELDS or k.lower() in ('filename', 'file name', 'command') or not v:
                if cur and not v:
                    pars.append(cur); cur = []
                continue
        cur.append(c)
    if cur:
        pars.append(cur)
    out = []
    for p in pars:
        t = ' '.join(p)
        if BOILER.search(t) or t.lower().startswith('retrieval info'):
            continue
        if sum(1 for l in p if CODEY.search(l)) > len(p) / 2:
            continue
        out.append(t)
    return out, fields, end_line


def not_vhdl(path, text, trunc):
    head = text[:400].lstrip()
    if re.match(r'(G0?4|G75|G90|%FS|%MO|%IN|%AD|D\d+\*|X-?\d+Y)', head):
        n = text.count('\n')
        ap = len(re.findall(r'%ADD\d+', text))
        units = 'inch' if '%MOIN' in text else ('mm' if '%MOMM' in text else '?')
        fs = re.search(r'%FS(\w+)\*%', text)
        return {'kind': 'data', 'type': 'Gerber photoplot (Eagle component-side layer, .cmp)',
                'meta': [('Lines', f'{n:,}'), ('Apertures', ap), ('Units', units)]
                        + ([('Format', fs.group(1))] if fs else []),
                'summary': 'Gerber RS-274X photoplot of the PCB component (top copper) side, exported from Eagle CAD. '
                           f'{ap} aperture definitions, {n:,} lines of plot data.',
                'keywords': ['Gerber', 'Eagle', 'component side', 'PCB'],
                'notes': ['Not VHDL: .cmp here is an Eagle CAM job output; plot coordinates not reproduced.']}
    r = {'kind': 'document', 'paragraphs': core.split_paragraphs(text)[:5000]}
    if not path.lower().endswith('.cmp') and re.search(r'\b(xor|and|or|not)\b|<=|=>', text[:20000], I):
        r['kind'] = 'source'
        r['type'] = 'VHDL code fragment (no entity/architecture)'
        tg = drive_targets(text[:20000]) or re.findall(r'^\s*(\w+)\s*<?=', text[:2000], re.M)
        r['summary'] = 'VHDL code fragment with no design units' + (f"; assigns {', '.join(tg[:10])}" if tg else '') + '.'
        r['code_lang'] = 'vhdl'
    if trunc:
        r['notes'] = ['File larger than 20 MB: text truncated.']
    return r


def extract(path):
    try:
        return _extract(path)
    except Exception as e:  # never raise
        try:
            text, trunc = core.read_text(path)
            r = {'kind': 'source', 'type': 'VHDL source', 'paragraphs': core.split_paragraphs(text)[:2000],
                 'notes': [f'VHDL parse failed ({type(e).__name__}); plain text shown.']}
            return r
        except Exception:
            return {'kind': 'binary', 'notes': ['Unreadable file.']}


def _extract(path):
    name = path.rsplit('/', 1)[-1].lower()
    isbin = core.looks_binary(path)
    text, trunc = ('', False) if isbin else core.read_text(path)
    sample = text[:8192]
    if isbin or (sample and sum(1 for ch in sample if ord(ch) > 126 or (ord(ch) < 32 and ch not in '\t\r\n\f')) > 0.15 * len(sample)):
        with open(path, 'rb') as f:
            head = f.read(16)
        return {'kind': 'binary', 'type': 'Encrypted / binary HDL (e.g. Altera-encrypted IP)',
                'summary': 'Encrypted or binary-encoded HDL file (typically vendor-encrypted IP such as Altera SignalTap / '
                           'MegaCore source); compiled by the vendor tool, not human-readable.',
                'notes': ['Content is encrypted/binary: no VHDL structure extracted.'],
                'meta': [('First bytes', '`' + head.hex(' ') + '`')]}
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    src = Src(text)
    code = src.code
    if not re.search(r'\b(entity|component|package|architecture)\s+\w+', code, I) and not INST.search(code):
        if name.endswith('.cmp') or not re.search(r'\b(library|use|signal|process)\b', code, I):
            return not_vhdl(path, text, trunc)

    tool, ip, facts = detect_tool(text, name)
    big = len(text) > 1_500_000
    funcs, outline, notes, meta = [], [], [], []
    spans = []                    # param/port list spans to exclude from signal/constant scans
    kw_extra = []

    # ---- design units
    units = []
    for m in UNIT.finditer(code):
        pre = code[max(0, m.start() - 12):m.start()].lower()
        if re.search(r'\bend\s*$', pre):
            continue
        if m.group(1):
            units.append(('entity', m.group(1), None, m))
        elif m.group(2):
            units.append(('architecture', m.group(2), m.group(3), m))
        elif m.group(5):
            units.append(('package body' if m.group(4) else 'package', m.group(5), None, m))
        else:
            units.append(('configuration', m.group(6), m.group(7), m))
    unit_starts = [u[3].start() for u in units] + [len(code)]

    def unit_end(idx):
        return unit_starts[idx + 1]

    def owner(off):
        k = bisect.bisect_right(unit_starts, off) - 1
        return units[k] if 0 <= k < len(units) else None

    entities = {}
    for idx, (k, nm, of, m) in enumerate(units):
        a, hard = m.start(), unit_end(idx)
        if k == 'entity':
            em = re.compile(r'\bend\b', I).search(code, m.end(), hard)
            b = em.start() if em else hard
            params = []
            for clause in ('generic', 'port'):
                hc = header_clause(code, m.end(), b, clause)
                if hc:
                    p0, body, q = hc
                    spans.append((p0, q))
                    params += parse_items(src, p0, body, generic=(clause == 'generic'))
            ee = re.compile(r';', I).search(code, b, hard) if em else None
            e_end = ee.end() if ee else b
            ports = [p for p in params if not p[1].startswith('generic')]
            entities[nm.lower()] = ports
            dirs = dir_count(ports)
            doc = src.doc_before(src.line(a), also_inline=False)
            funcs.append({'name': nm, 'kind': 'entity', 'line': src.line(a),
                          'signature': src.src_slice(a, e_end, 30),
                          'doc': (doc + ' ' if doc else '') + f"{len(ports)} ports ("
                                 + dirs + ')'
                                 + (f", {len(params) - len(ports)} generics" if len(params) > len(ports) else '') + '.',
                          'params': params[:400]})
            if len(params) > 400:
                notes.append(f'Entity {nm}: {len(params)} ports/generics, table capped at 400.')
            kw_extra.append(nm)
        elif k in ('package', 'package body'):
            doc = src.doc_before(src.line(a), also_inline=False)
            funcs.append({'name': nm, 'kind': k, 'line': src.line(a), 'signature': ws(m.group(0)),
                          'doc': doc, '_span': (a, hard)})
            kw_extra.append(nm)
        elif k == 'configuration':
            funcs.append({'name': f'{nm} of {of}', 'kind': 'configuration', 'line': src.line(a),
                          'signature': ws(m.group(0))})
        else:
            doc = src.doc_before(src.line(a), also_inline=False)
            funcs.append({'name': f'{nm} of {of}', 'kind': 'architecture', 'line': src.line(a),
                          'signature': ws(m.group(0)), 'doc': doc, '_span': (a, hard), '_arch': (nm, of)})

    # ---- component declarations
    comps = []
    for m in COMP.finditer(code):
        pre = code[max(0, m.start() - 12):m.start()].lower()
        if re.search(r'\bend\s*$', pre):
            continue
        em = re.compile(r'\bend\s+component\b[^;]*;?', I).search(code, m.end(), m.end() + 400000)
        b = em.start() if em else min(len(code), m.end() + 2000)
        params = []
        for clause in ('generic', 'port'):
            hc = header_clause(code, m.end(), b, clause)
            if hc:
                p0, body, q = hc
                spans.append((p0, q))
                params += parse_items(src, p0, body, generic=(clause == 'generic'))
        u = owner(m.start())
        where = f' (declared in {u[0]} {u[1]})' if u else ''
        comps.append(m.group(1))
        funcs.append({'name': m.group(1), 'kind': 'component', 'line': src.line(m.start()),
                      'signature': src.src_slice(m.start(), em.end() if em else b, 30),
                      'doc': (src.doc_before(src.line(m.start()), False) + ' ').lstrip()
                             + f'Component declaration{where}, {len(params)} ports/generics.',
                      'params': params[:400]})

    # ---- functions / procedures
    subs = []
    for m in SUBP.finditer(code):
        pre = code[max(0, m.start() - 12):m.start()].lower()
        if re.search(r'\bend\s*$', pre):
            continue
        j = m.end()
        while j < len(code) and code[j] in ' \t\n':
            j += 1
        params = []
        if j < len(code) and code[j] == '(':
            q = match_paren(code, j)
            spans.append((j + 1, q))
            params = parse_items(src, j + 1, code[j + 1:q])
            j = q + 1
        rm = re.compile(r'\s*return\s+([\w\.]+)', I).match(code, j)
        ret = ''
        if rm:
            ret = rm.group(1); j = rm.end()
        tm = re.compile(r'\s*(is\b|;)', I).match(code, j)
        is_body = bool(tm and tm.group(1).lower() == 'is')
        kind = m.group(2).lower()
        nm = m.group(3)
        if m.group(1):
            kind = m.group(1).lower() + ' ' + kind
        sig = ws(code[m.start():j]) + (' is' if is_body else ';')
        u = owner(m.start())
        subs.append({'name': nm, 'kind': kind + ('' if is_body else ' declaration'), 'line': src.line(m.start()),
                     'signature': sig, 'doc': src.doc_before(src.line(m.start())), 'params': params,
                     'returns': ret, '_body': is_body, '_n': len(params),
                     '_where': f'{u[0]} {u[1]}' if u else ''})
    bodies = {(s['name'].lower(), s['_n']) for s in subs if s['_body']}
    sub_names = {s['name'].lower() for s in subs}
    for s in subs:
        if not s['_body'] and (s['name'].lower(), s['_n']) in bodies:
            continue
        if s['_where']:
            s['doc'] = (s['doc'] + f' (in {s["_where"]})').strip()
        funcs.append(s)

    # ---- processes
    pn = 0
    n_arch = sum(1 for u in units if u[0] == 'architecture')
    proc_spans = []
    edge_re = re.compile(r'\b(rising_edge|falling_edge)\s*\(\s*(\w+)\s*\)|\b(\w+)\s*\'\s*event\s+and\s+\3\s*=\s*\'([01])\'', I)
    for m in PROC.finditer(code):
        pre = code[max(0, m.start() - 60):m.start()]
        if re.search(r'\bend\s+(postponed\s+)?$', pre, I):
            continue
        lm = re.search(r'(\w+)\s*:\s*(postponed\s+)?$', pre, I)
        label = lm.group(1) if lm and lm.group(1).lower() not in KEYWORDS else ''
        st = m.start() - (len(pre) - lm.start()) if label else m.start()
        j = m.end()
        while j < len(code) and code[j] in ' \t\n':
            j += 1
        sens = []
        if j < len(code) and code[j] == '(':
            q = match_paren(code, j)
            sens = [ws(x) for x in code[j + 1:q].split(',') if x.strip()]
            j = q + 1
        pn += 1
        em = re.compile(r'\bend\s+(postponed\s+)?process\b[^;]*;?', I).search(code, j)
        e = em.end() if em else len(code)
        body = code[j:e]
        proc_spans.append((st, e))
        bm = re.compile(r'\bbegin\b', I).search(body)
        decl_end = j + bm.end() if bm else j
        edges = []
        for x in edge_re.finditer(body):
            if x.group(1):
                edges.append(f'{x.group(1).lower()}({x.group(2)})')
            else:
                edges.append(f"{'rising' if x.group(4) == '1' else 'falling'}_edge({x.group(3)})")
        edges = list(dict.fromkeys(edges))
        drives = drive_targets(body)
        calls = [c for c in dict.fromkeys(w.lower() for w in re.findall(r'\b(\w+)\s*\(', body)) if c in sub_names]
        u = owner(m.start())
        nm = label or (f"process({', '.join(sens)[:60]}) #{pn}" if sens else f'process #{pn}')
        doc = src.doc_before(src.line(st))
        bits = []
        if edges:
            bits.append('Clocked on ' + ', '.join(edges[:4]) + '.')
        elif sens:
            bits.append('Combinational / level-sensitive.')
        if drives:
            bits.append('Drives: ' + ', '.join(drives[:30]) + (' …' if len(drives) > 30 else '') + '.')
        if u and u[0] == 'architecture' and n_arch > 1:
            bits.append(f'In architecture {u[1]} of {u[2]}.')
        nlines = src.line(e) - src.line(st) + 1
        bits.append(f'{nlines} lines.')
        funcs.append({'name': nm, 'kind': 'process', 'line': src.line(st),
                      'signature': src.src_slice(st, decl_end, 25),
                      'doc': (sentence(doc) + ' ' + ' '.join(bits)).strip(),
                      'params': [(s, 'sensitivity', '') for s in sens], 'calls': calls})

    # ---- instances
    insts = []
    for m in INST.finditer(code):
        lab = m.group(1)
        if lab.lower() in KEYWORDS:
            continue
        if m.group(2):
            tgt = m.group(3) + (f'({m.group(4)})' if m.group(4) else '')
            short = m.group(3).split('.')[-1]
        else:
            tgt = m.group(6); short = tgt.split('.')[-1]
            if short.lower() in KEYWORDS:
                continue
        insts.append((m.start(), lab, tgt, short, m))
    by_arch = collections.defaultdict(list)
    for off, lab, tgt, short, m in insts:
        by_arch[bisect.bisect_right(unit_starts, off) - 1].append(short)
    for f in funcs:
        if f.get('kind') == 'architecture':
            idx = unit_starts.index(f['_span'][0])
            cs = by_arch.get(idx, [])
            cnt = collections.Counter(cs)
            order = list(dict.fromkeys(cs))
            if len(order) > 60:
                order = [c for c, _ in cnt.most_common()]
            f['calls'] = order
            a, b = f['_span']
            nproc = sum(1 for g in funcs if g.get('kind') == 'process' and a <= _off(src, g['line']) < b)
            parts = []
            if cs:
                parts.append(f'{len(cs)} instance(s) of {len(order)} component(s): '
                             + ', '.join(f'{c} ×{n}' for c, n in cnt.most_common(8)) + (' …' if len(cnt) > 8 else ''))
            if nproc:
                parts.append(f'{nproc} process(es)')
            f['doc'] = (f.get('doc', '') + ' ' + ('; '.join(parts) + '.' if parts else '')).strip()
            # concurrent statements = arch body minus process bodies
            body = code[a:b]
            for pa, pb in proc_spans:
                if a <= pa < b:
                    body = body[:pa - a] + ' ' * (min(pb, b) - pa) + body[min(pb, b) - a:]
            conc = drive_targets(body)
            if not cs and not nproc and not conc and not re.search(r'\bbegin\b.*\w.*\bend\b', body[-4000:], I | re.S):
                f['doc'] = (f['doc'] + ' Empty architecture body.').strip()
            if conc:
                f['doc'] += ' Concurrent assignments drive: ' + ', '.join(conc[:30]) + (' …' if len(conc) > 30 else '') + '.'
            gens = len(re.findall(r'\bgenerate\b', body, I)) // 2
            if gens:
                f['doc'] += f' {gens} generate block(s).'
            nl = src.line(b) - src.line(a) + 1
            if nl <= 45:
                f['signature'] = src.src_slice(a, b, 45).rstrip()
            else:
                f['doc'] += f' {nl} lines.'

    # ---- packages: list declared items
    for f in funcs:
        if f.get('kind') in ('package', 'package body'):
            a, b = f['_span']
            items = [s['name'] for s in subs if a <= _off(src, s['line']) < b]
            f['calls'] = list(dict.fromkeys(items))
            nc, nt = len(CONST.findall(code, a, b)), len(TYPE.findall(code, a, b))
            ncomp = sum(1 for g in funcs if g['kind'] == 'component' and a <= _off(src, g['line']) < b)
            bits = [f'{n} {w}' for n, w in ((nc, 'constant(s)'), (nt, 'type(s)'), (ncomp, 'component(s)'),
                                           (len(f['calls']), 'subprogram(s)')) if n]
            if bits:
                f['doc'] = (f.get('doc', '') + ' Declares ' + ', '.join(bits) + '.').strip()
    spans.sort()
    sstarts = [s[0] for s in spans]

    # ---- outline
    libs = list(dict.fromkeys(ws(x) for m in LIB.finditer(code) for x in m.group(1).split(',')))
    uses = list(dict.fromkeys(ws(m.group(1)) for m in USE.finditer(code)))
    if libs or uses:
        outline.append({'heading': 'Libraries and use clauses'})
        outline += [f'library `{l}`' for l in libs[:40]] + [f'use `{u}`' for u in uses[:60]]
        kw_extra += [u.split('.')[0] for u in uses if u.split('.')[0].lower() not in ('ieee', 'std', 'work')]

    def decl_scan(rx, cap):
        rows, total = [], 0
        for m in rx.finditer(code):
            if in_spans(spans, sstarts, m.start()):
                continue
            pre = code[max(0, m.start() - 10):m.start()]
            names = [ws(n) for n in m.group(1).split(',') if n.strip()]
            total += len(names)
            if len(rows) < cap:
                t = m.group(2); v = ''
                if ':=' in t:
                    t, v = t.split(':=', 1)
                rows.append((', '.join(names), ws(t), ws(v), src.line(m.start())))
        return rows, total

    sigs, nsig = decl_scan(SIG, MAX_SIG)
    if sigs:
        outline.append({'heading': f'Signals ({nsig})'})
        for n, t, v, ln in sigs:
            c = src.comments.get(ln, '')
            outline.append(f'`{n}` : {t}' + (f' := {v[:60]}' if v else '') + f' (line {ln})'
                           + (f' — {c[:120]}' if c and not DECOR.match(c) else ''))
        if nsig > len(sigs):
            outline.append(f'… {nsig - len(sigs)} more signals not listed.')
    consts, ncon = decl_scan(CONST, 150)
    if consts:
        outline.append({'heading': f'Constants ({ncon})'})
        for n, t, v, ln in consts:
            c = src.comments.get(ln, '')
            outline.append(f'`{n}` : {t}' + (f' := {v[:100]}' if v else '') + f' (line {ln})'
                           + (f' — {c[:120]}' if c and not DECOR.match(c) else ''))
        if ncon > len(consts):
            outline.append(f'… {ncon - len(consts)} more constants not listed.')
    types = []
    for m in TYPE.finditer(code):
        rest = code[m.end():m.end() + 20000]
        if re.match(r'record\b', rest, I):
            em = re.search(r'\bend\s+record\b', rest, I)
            body = rest[:em.end()] if em else rest[:400]
        else:
            body = rest.split(';', 1)[0]
        tl = src.line(m.start())
        td = src.doc_before(tl)
        types.append(f"{m.group(1).lower()} `{m.group(2)}` is {ws(body)[:200]} (line {tl})" + (f' — {td[:160]}' if td else ''))
        if len(types) >= 150:
            break
    if types:
        outline.append({'heading': f'Types ({len(types)})'})
        outline += types
    if insts:
        outline.append({'heading': f'Instances ({len(insts)})'})
        for off, lab, tgt, short, m in insts[:MAX_INST]:
            outline.append(f'`{lab}` : {tgt} (line {src.line(off)})')
        if len(insts) > MAX_INST:
            outline.append(f'… {len(insts) - MAX_INST} more instances not listed (capped at {MAX_INST}).')
            notes.append(f'{len(insts):,} instances; list capped at {MAX_INST}.')
        cnt = collections.Counter(i[3] for i in insts)
        if len(insts) > 20:
            outline.append({'heading': 'Instance counts by component'})
            outline += [f'`{c}` × {n}' for c, n in cnt.most_common(60)]
        kw_extra += [c for c, _ in cnt.most_common(10)]

    if insts and not units and not comps and len(insts) <= 50:
        for off, lab, tgt, short, m in insts:
            params = []
            p = m.end()
            while True:
                p2 = code.find('(', p)
                if p2 < 0 or code[p:p2].strip():
                    break
                q = match_paren(code, p2)
                for _, a in split_top(code[p2 + 1:q], ','):
                    if '=>' in a:
                        fm, ac = a.split('=>', 1)
                        params.append((ws(fm), '=> ' + ws(ac), ''))
                    else:
                        params.append((ws(a), 'positional', ''))
                nx = re.compile(r'\s*port\s+map\s*', I).match(code, q + 1)
                if not nx:
                    break
                p = nx.end()
            funcs.append({'name': lab, 'kind': 'instance', 'line': src.line(off),
                          'signature': src.src_slice(off, q + 2 if params else m.end(), 30),
                          'doc': f'Instantiation of {tgt}' + (' (template).' if lab.lower().endswith('_inst') or
                                                               lab.lower().startswith('your_') else '.'),
                          'params': params, 'calls': [short]})
        typ_inst = True
    else:
        typ_inst = False

    # MegaWizard / IP parameters: generic map of the first instance
    mf = {}
    if tool.startswith('Altera') and insts:
        m = insts[0][4]
        p = code.find('(', m.end()) if m.group(7).lower() == 'generic' else -1
        if p >= 0 and not code[m.end():p].strip():
            q = match_paren(code, p)
            kv = [ws(x) for _, x in split_top(code[p + 1:q], ',')]
            if kv:
                outline.append({'heading': f'Megafunction parameters ({insts[0][2]})'})
                outline += [f'`{x}`' for x in kv[:120]]
                for x in kv:
                    if '=>' in x:
                        k_, v_ = x.split('=>', 1)
                        mf[k_.strip().lower()] = v_.strip().strip('"')
                    xm = re.match(r'intended_device_family\s*=>\s*"([^"]+)"', x, I)
                    if xm:
                        meta.append(('Device family', xm.group(1)))
                        kw_extra.append(xm.group(1))

    # ---- header, summary, comments
    hdr, fields, hdr_end = header_comments(src)
    seen_f = set()
    for k, v in fields:
        if k.lower() in META_FIELDS and k.lower() not in seen_f:
            seen_f.add(k.lower())
            v = re.sub(r'\$(?:Date|Revision|Author|Id|RCSfile):?\s*([^$]*?)\s*\$', r'\1', v).strip()
            if v:
                meta.append((k, v[:200]))
    ents = [f['name'] for f in funcs if f['kind'] == 'entity']
    archs = [f for f in funcs if f['kind'] == 'architecture']
    procs = [f for f in funcs if f['kind'] == 'process']
    pk = [f['name'] for f in funcs if f['kind'] in ('package', 'package body')]
    sp = [f['name'] for f in funcs if 'function' in f['kind'] or 'procedure' in f['kind']]
    struct = []
    if len(ents) == 1:
        ports = entities.get(ents[0].lower(), [])
        struct.append(f"defines entity {ents[0]}" + (f" ({len(ports)} ports: {dir_count(ports)})" if ports else ''))
    elif ents:
        used = {i[3].lower() for i in insts}
        tops = [e for e in ents if e.lower() not in used] or ents
        top = tops[-1]
        ports = entities.get(top.lower(), [])
        struct.append(f"defines {len(ents)} entities ({', '.join(ents[:6])}{' …' if len(ents) > 6 else ''}); "
                      f"top-level {top}" + (f" ({len(ports)} ports: {dir_count(ports)})" if ports else ''))
    if len(archs) == 1:
        struct.append(f"architecture {archs[0]['_arch'][0]}" + ('' if ents else f" of {archs[0]['_arch'][1]}"))
    elif archs:
        struct.append(f"{len(archs)} architectures")
    if pk:
        struct.append(f"package {', '.join(dict.fromkeys(pk))}")
    if procs:
        struct.append(f'{len(procs)} process(es)')
    if sp:
        spc = collections.Counter(sp)
        struct.append(f"{len(sp)} function(s)/procedure(s): " + ', '.join(n + (f' ×{c}' if c > 1 else '') for n, c in list(spc.items())[:8])
                      + (' …' if len(spc) > 8 else ''))
    if insts:
        cnt = collections.Counter(i[3] for i in insts)
        tmpl = ' (instantiation template)' if typ_inst or any(i[1].lower().startswith('your_inst') for i in insts) else ''
        struct.append(f"{len(insts)} instance(s){tmpl} of " + ', '.join(f'{c}' + (f' ×{n}' if n > 1 else '')
                                                               for c, n in cnt.most_common(8))
                      + (' …' if len(cnt) > 8 else ''))
    if comps and not ents:
        cf = [f for f in funcs if f['kind'] == 'component']
        struct.append('declares component ' + '; '.join(
            f"{f['name']} ({dir_count([p for p in f.get('params', []) if not p[1].startswith('generic')])})"
            for f in cf[:6]) + (' …' if len(cf) > 6 else ''))
    struct_s = sentence('; '.join(struct)) if struct else ''
    if struct_s:
        struct_s = struct_s[0].upper() + struct_s[1:]
    desc = [v for k, v in fields if k.lower() in ('description', 'desc', 'function', 'title')
            or (k.lower() == 'purpose' and not tool)]
    desc += [v for k, v in facts if k == 'Core description']
    hdr = [re.sub(r'\$(Revision|Date|Id|Header|Author|Log|RCSfile|Source)[^$]*\$', '', h).strip() for h in hdr]
    hdr = [h for h in hdr if len(h) > 3 and not re.match(r'(revision|rev\.?\s*\d|\$log|modification|history|change log)', h, I) and h.count('|') < 4
           and sum(ch.isalpha() for ch in h) > 0.5 * len(h)]
    if tool and not tool.startswith('Tool-generated'):
        hdr = []          # vendor-tool headers are boilerplate
    h2 = []
    for h in hdr:
        for d in desc:
            h = h.replace(d, ' ')
        h = ws(re.sub(r'\b(Module Description|Description of module|Description|Desc)\s*:\s*', ' ', h, flags=I))
        if len(h) > 3:
            h2.append(h)
    lead = ' '.join(sentence(x) for x in desc + h2)
    if len(lead) > 500:
        lead = lead[:500].rsplit(' ', 1)[0] + ' …'
    if tool:
        bits = ['Altera Quartus / MAX+PLUS II component declaration file' if tool == 'Altera component declaration'
                else f"Generated by {tool[16:-1] if tool.startswith('Tool-generated (') else tool}" + (f" {ip} megafunction" if ip and tool.startswith('Altera') else (f' {ip}' if ip else ''))
                + (f" ({ents[0] if ents else comps[0]})" if (ents or comps) else '')]
        ver = dict(facts).get('Quartus version')
        if ver:
            bits.append('Quartus ' + ver.split(' SJ')[0])
        fam = mf.get('intended_device_family')
        if fam:
            bits.append(fam)
        lead_tool = sentence(', '.join(bits))
        lead = (lead_tool + ' ' + lead).strip()
    mfs = mf_summary(mf)
    if mfs:
        lead += ' ' + mfs
    summary = (lead + ' ' + struct_s).strip()

    # comment paragraphs (documentation only)
    pars, cur, total = [], [], 0
    for ln in range(hdr_end if (tool and not tool.startswith('Tool-generated')) else 1, len(src.lines) + 1):
        c = src.comments.get(ln)
        if c and c[:1] in '/\\':
            c = re.sub(r'^[\s/\\_|]+', '', c)
        if c is None or not c or DECOR.match(c) or CODEY.search(c) or c.lower().startswith('retrieval info') \
                or (FIELD.match(c) and FIELD.match(c).group(1).lower() in META_FIELDS | {'filename', 'file name', 'command'}) \
                or re.match(r'(synopsys|synthesis|pragma|altera|xilinx|rtl_synthesis|translate_o)\w*\s+\w+\s*$', c, I):
            if cur:
                t = '\n'.join(cur)
                if not BOILER.search(t):
                    pars.append(t); total += len(t)
                cur = []
            if total > 300_000 or len(pars) > 3000:
                notes.append('Comment text truncated.')
                break
            continue
        cur.append(c)
    if cur and not BOILER.search('\n'.join(cur)):
        pars.append('\n'.join(cur))
    if pars:
        pars.insert(0, {'heading': 'Source comments'})

    kw_extra += [f['name'] for f in funcs if f['kind'] in ('component', 'package', 'function', 'procedure',
                                                            'pure function', 'impure function')][:6]
    kw_extra += [f['name'] for f in funcs if f['kind'] == 'process' and not f['name'].startswith('process')][:4]
    ctext = ' '.join(desc + hdr + [p for p in pars if isinstance(p, str)])[:200_000]
    kw_extra = list(dict.fromkeys(k for k in ([ip] if ip else []) + kw_extra if k))[:10]
    kws = core.keywords(ctext, kw_extra, n=15) if ctext.strip() else kw_extra
    if len(kws) < 15:
        # pad with distinctive port / signal names (one per numbered family: in1, in2 ... -> in1)
        cand = [p[0] for f in funcs if f['kind'] in ('entity', 'component') for p in (f.get('params') or [])]
        cand += [re.split(r'\s*,\s*', o.split('`')[1])[0] for o in outline
                 if isinstance(o, str) and o.startswith('`') and ' : ' in o]
        stems = set(k.lower() for k in kws)
        for c in cand:
            st = re.sub(r'_?\d+$', '', c).lower()
            if st in stems or c.lower() in stems or len(c) < 3:
                continue
            stems.add(st); kws.append(c)
            if len(kws) >= 15:
                break

    # ---- type / meta
    typ = 'VHDL source'
    if name.endswith('.cmp'):
        typ = 'VHDL component declaration (Quartus / MAX+PLUS II .cmp)'
    elif name.endswith('.vho'):
        typ = 'VHDL instantiation template / output netlist (.vho)'
    elif name.endswith('.vhf'):
        typ = 'VHDL netlist from schematic (.vhf)'
    elif name.endswith('.vht'):
        typ = 'VHDL test bench (.vht)'
    elif name.endswith(('~', '#')):
        typ = 'VHDL source (editor backup/autosave)'
    if typ_inst:
        typ = 'VHDL instantiation template'
    if tool and not (name.endswith('.cmp') and tool == 'Altera component declaration'):
        typ += f' — {tool}' + (f' ({ip})' if ip else '')
    meta = facts + meta
    if tool:
        meta.insert(0, ('Generated by', tool))
    meta.append(('Lines', f'{len(src.lines):,}'))
    counts = collections.Counter(f['kind'] for f in funcs)
    meta.append(('VHDL units', ', '.join(f'{v} {k}' for k, v in counts.most_common()) or 'none found'))
    if big:
        notes.append('Large file: netlist summarised; long lists capped.')
    if trunc:
        notes.append('File larger than 20 MB: parsed text truncated.')
    for f in funcs:
        for k in [k for k in f if k.startswith('_')]:
            del f[k]
    funcs.sort(key=lambda f: f.get('line') or 0)
    if len(funcs) > 2000:
        notes.append(f'{len(funcs)} routines; only first 2000 listed.')
        funcs = funcs[:2000]
    return {'kind': 'source', 'type': typ, 'title': ents[0] if ents else (comps[0] if comps else (pk[0] if pk else None)),
            'meta': meta, 'summary': summary, 'keywords': kws,
            'functions': funcs, 'outline': outline, 'paragraphs': pars, 'code_lang': 'vhdl', 'notes': notes}


TARGET = re.compile(r'(?:[;\n]|\bthen|\belse|\bbegin|=>|\bloop|\bgenerate|:)\s*(\w+)\s*(?:\([^;<()]*(?:\([^;<()]*\)[^;<()]*)*\)\s*)?$', I)


def drive_targets(body):
    """Signals on the left of '<=' (statement starts only, not comparisons)."""
    out = {}
    for m in re.finditer('<=', body):
        pre = ('\n' if m.start() <= 160 else '') + body[max(0, m.start() - 160):m.start()]
        t = TARGET.search(pre)
        if t and t.group(1).lower() not in KEYWORDS and not t.group(1)[0].isdigit():
            out.setdefault(t.group(1), None)
    return list(out)


def sentence(x):
    x = x.strip()
    return x if not x or x[-1] in '.!?:;…' else x + '.'


def mf_summary(mf):
    if not mf:
        return ''
    out = []
    try:
        per = float(mf.get('inclk0_input_frequency', '0') or 0)
    except ValueError:
        per = 0
    if per:
        fin = 1e6 / per
        out.append(f'inclk0 {fin:.4g} MHz ({per:g} ps)')
        for n in range(10):
            mul, div = mf.get(f'clk{n}_multiply_by'), mf.get(f'clk{n}_divide_by')
            if mul and div:
                try:
                    f = fin * float(mul) / float(div)
                    ph = mf.get(f'clk{n}_phase_shift', '0')
                    out.append(f'c{n} = {f:.4g} MHz (×{mul}/{div}' + (f', phase {ph} ps' if ph not in ('0', '') else '') + ')')
                except ValueError:
                    pass
    for k in ('lpm_type', 'operation_mode', 'lpm_width', 'lpm_widthu', 'lpm_numwords', 'lpm_widthad',
              'width_a', 'widthad_a', 'numwords_a', 'width_b', 'numwords_b', 'lpm_direction', 'lpm_pipeline',
              'lpm_shiftout', 'lpm_showahead', 'init_file', 'lpm_cvalue', 'lpm_representation'):
        if k in mf and not (k == 'operation_mode' and per):
            out.append(f'{k} = {mf[k]}')
    return ('Settings: ' + '; '.join(out[:12]) + '.') if out else ''


def dir_count(ports):
    c = collections.Counter(p[1].split(' ')[0] for p in ports)
    order = ['in', 'out', 'inout', 'buffer', 'linkage']
    ks = [k for k in order if k in c] + [k for k in c if k not in order]
    return ', '.join(f'{c[k]} {k}' for k in ks)


def _off(src, line):
    return src.nl[line - 2] + 1 if line >= 2 and line - 2 < len(src.nl) else 0
