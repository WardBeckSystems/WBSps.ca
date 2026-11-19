"""Verilog / SystemVerilog extractor.

Breaks a Verilog-family file into modules (ports + parameters), functions,
tasks, always/initial blocks and submodule instances. Recognises tool-generated
files (Quartus MegaWizard wrappers, Synplify/Quartus VQM netlists, Xilinx
sch2hdl .vf schematics, CORE Generator .veo templates) and summarises them.
"""
import os, re, bisect, collections

import core

EXTS = {'v', 'sv', 'svh', 'vh', 'vt', 'veo', 'vqm', 'vf', 'vo', 'v~', 'v~~', 'v#', 'vlog', 'vg'}

MAX_FUNCS = 1500
MAX_PARAMS = 400
MAX_INST_OUTLINE = 200

KEYWORDS = set("""always always_ff always_comb always_latch and assign automatic begin buf bufif0 bufif1 case casex casez
cell cmos config deassign default defparam design disable edge else end endcase endconfig endfunction endgenerate
endmodule endprimitive endspecify endtable endtask event for force forever fork function generate genvar highz0
highz1 if ifnone incdir include initial inout input instance integer join join_any join_none large liblist library
localparam macromodule medium module nand negedge nmos nor noshowcancelled not notif0 notif1 or output parameter
pmos posedge primitive pull0 pull1 pulldown pullup pulsestyle_onevent pulsestyle_ondetect rcmos real realtime reg
release repeat rnmos rpmos rtran rtranif0 rtranif1 scalared showcancelled signed small specify specparam strong0
strong1 supply0 supply1 table task time tran tranif0 tranif1 tri tri0 tri1 triand trior trireg unsigned use uwire
vectored wait wand weak0 weak1 while wire wor xnor xor logic bit byte shortint int longint typedef enum struct
union packed import export package endpackage interface endinterface modport class endclass virtual extends
return break continue unique priority final assert assume cover property sequence program endprogram var const
static string void ref clocking endclocking inside with foreach do bind""".split())
GATES = {'and', 'or', 'nand', 'nor', 'xor', 'xnor', 'buf', 'not', 'bufif0', 'bufif1', 'notif0', 'notif1'}

LICENSE = re.compile(r'warrant|liabil|licen[cs]e|all rights reserved|copyright|\(c\)|proprietary|do not edit|'
                     r'expressly|merchantab|infring|disclaim|agreement|confidential|without limitation|'
                     r'sold by|ampp|subscription|not intended for use in life|wizard-generated|'
                     r'distributed|permission is hereby|free software|gnu general', re.I)
HDR_FIELD = re.compile(r'^\s*(Written by|Designed by|Coded by|Created by|Modified by|Company|Engineer|Author|Authors|Designer|Create Date|Created|Date Created|Date|'
                       r'Last Modified|Date Last Modified|Design Name|Module Name|Module|Project Name|Project|'
                       r'Target Devices?|Device|Tool versions?|Tools?|Description|Dependencies|Revision|Rev|'
                       r'Additional Comments|Purpose|Vendor|Version|Application|File ?name|File Name|Function|'
                       r'Overview|Abstract|Notes?|Summary|Language|Simulator|Synthesis|Comments?)\s*:\s*(.*)$', re.I)
DESC_FIELDS = {'description', 'purpose', 'function', 'overview', 'abstract', 'summary', 'additional comments',
               'comments', 'comment', 'notes', 'note'}
META_FIELDS = {'written by': 'Author', 'designed by': 'Author', 'coded by': 'Author', 'created by': 'Author',
               'modified by': 'Modified by', 'company': 'Company', 'engineer': 'Engineer', 'author': 'Author', 'authors': 'Author',
               'designer': 'Author', 'create date': 'Created', 'created': 'Created', 'date created': 'Created',
               'date': 'Date', 'last modified': 'Last modified', 'date last modified': 'Last modified',
               'project name': 'Project', 'project': 'Project', 'target devices': 'Target device',
               'target device': 'Target device', 'device': 'Device', 'tool versions': 'Tool versions',
               'tool version': 'Tool versions', 'vendor': 'Vendor', 'version': 'Version',
               'application': 'Application', 'revision': 'Revision', 'rev': 'Revision'}

TOKEN_RX = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"|\(\*(?!\s*\))(?:(?!\*\)).){0,2000}?\*\)', re.S)
DIRECTIVE_RX = re.compile(r'^[ \t]*`(\w+)([^\n]*)', re.M)
UNIT_RX = re.compile(r'(?<![\w$`])(module|macromodule|interface|program|package|primitive)\s+(?:automatic\s+|static\s+)?([A-Za-z_][\w$]*)')
FUNC_RX = re.compile(r'(?<![\w$`])(function|task)\b')
ALWAYS_RX = re.compile(r'(?<![\w$`])(always_ff|always_comb|always_latch|always|initial|final)\b')
BLOCK_TOK = re.compile(r'(?<![\w$])(begin|end|case|casex|casez|randcase|endcase|fork|join|join_any|join_none)(?![\w$])|;|\(')
INST_HEAD = re.compile(r'(?<![\w$`\'.\\])([A-Za-z_][\w$]*)(?![\w$])[ \t\r\n]*(?=[#\\A-Za-z_])')
WIZ_HDR = re.compile(r'(?i)^(megafunction wizard|GENERATION:|VERSION: WM|MODULE:|File Name:|Megafunction Name|'
                     r'Simulation Library|\d+\.\d+(\.\d+)? Build \d+|Revision 0\.01 - File Created)')
BOILER = re.compile(r'translate_off|synthesis tools?\b|wrapper file|simulation librar|XilinxCoreLib|'
                    r'this file is owned|CORE Generator Help|must be compiled|instructions, please refer|'
                    r'should be performed by re-running|regenerating the core', re.I)
CODEISH = re.compile(r';\s*$|<=|^\s*(end|begin|else|if\s*\(|assign|always|wire|reg|input|output|case|endcase|default\s*:)\b|^\s*[\w\[\]:]+\s*=\s*[^=]+;')
PRAGMA = re.compile(r'^\s*(synopsys|synthesis|pragma|altera\s+(message|attribute)|translate_o|exemplar|'
                    r'cadence|xilinx\s+translate|VERSION_BEGIN|VERSION_END|Retrieval info|'
                    r'synthesis_resources|lint_|spyglass|verilator|coverage|INST_TAG)', re.I)
IDENT = re.compile(r'\\\S+|[A-Za-z_][\w$]*')
PAREN = re.compile(r'[()]')
DECL_RX = re.compile(r'(?<![\w$`])(input|output|inout)\b([^;]*);')
REGDECL_RX = re.compile(r'(?<![\w$`])(reg|logic)\b([^;]*);')
PARAM_RX = re.compile(r'(?<![\w$`])(parameter|localparam)\b([^;]*);')
DEFPARAM_RX = re.compile(r'(?<![\w$`])defparam\b([^;]*);')
TYPE_WORDS = {'wire', 'reg', 'logic', 'signed', 'unsigned', 'tri', 'tri0', 'tri1', 'wand', 'wor', 'supply0',
              'supply1', 'integer', 'bit', 'var', 'byte', 'int', 'shortint', 'longint', 'real', 'time',
              'uwire', 'triand', 'trior', 'trireg', 'string'}


# ------------------------------------------------------------------ helpers
def _ws(s):
    return re.sub(r'\s+', ' ', s).strip()


def _skip_ws(code, i):
    n = len(code)
    while i < n and code[i] in ' \t\r\n':
        i += 1
    return i


def _match_paren(code, i, limit=None):
    """code[i] == '('; return index just after the matching ')' (or len)."""
    depth = 0
    end = len(code) if limit is None else limit
    for m in PAREN.finditer(code, i, end):
        if m.group() == '(':
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return m.end()
    return end


def _split_top(s, sep=','):
    out, depth, cur = [], 0, []
    start = 0
    for i, ch in enumerate(s):
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth -= 1
        elif ch == sep and depth == 0:
            out.append((start, s[start:i]))
            start = i + 1
    out.append((start, s[start:]))
    return out


def _mhz(v):
    s = f'{v:.3f}'.rstrip('0').rstrip('.')
    return s + ' MHz'


def _num(v):
    try:
        v = str(v).strip().strip('"')
        m = re.match(r"^\d*'[sS]?[dD](\d+)$", v)
        if m:
            return float(m.group(1))
        return float(v)
    except Exception:
        return None


def _clean_comment(raw):
    """Comment token -> list of text lines without comment markers/box art."""
    if raw.startswith('//'):
        body = [raw[2:]]
    else:
        body = raw[2:-2].split('\n')
    out = []
    for ln in body:
        s = ln.strip()
        s = re.sub(r'^[/*#!\s]+', '', s)
        s = re.sub(r'[/*#\s]+$', '', s)
        s = re.sub(r'^[_=~\-]{3,}\s*|\s*[_=~\-]{3,}$', '', s).strip()
        out.append(s)
    return out


def _decorative(s):
    if not s:
        return True
    alpha = sum(c.isalnum() for c in s)
    return alpha < 3 or alpha / len(s) < 0.35


# ------------------------------------------------------------------ main
def extract(path):
    try:
        return _extract(path)
    except Exception as e:  # never raise
        return {'kind': 'source', 'type': 'Verilog HDL source', 'code_lang': 'verilog',
                'notes': [f'Verilog parser error ({type(e).__name__}: {str(e)[:100]}); partial results.']}


def _extract(path):
    name = os.path.basename(path)
    ext = name.rsplit('.', 1)[1].lower() if '.' in name else ''
    size0 = os.path.getsize(path)
    if size0 == 0:
        return {'kind': 'source', 'type': 'Empty Verilog file', 'summary': 'Empty file (0 bytes).',
                'notes': ['File is empty.']}
    with open(path, 'rb') as f:
        head = f.read(4096)
    if head.startswith(b'XSym\n'):
        ls_ = head.decode('latin-1').split('\n')
        tgt = ls_[3].strip() if len(ls_) > 3 else ''
        lock = name.startswith('.#')
        return {'kind': 'binary', 'type': 'XSym symbolic-link stub' + (' (Emacs lock file)' if lock else ''),
                'summary': ('Emacs edit-lock file' if lock else 'Symbolic link') + ' stored as a macOS/SMB "XSym" stub'
                           + (f' pointing to `{tgt}`' if tgt else '') + '; contains no Verilog code.',
                'meta': [('Link target', f'`{tgt}`')] if tgt else []}
    if core.looks_binary(path):
        if head.startswith(b'\x8b\x13\x9c/'):
            typ, summ = ('Altera-encrypted Verilog (protected IP)',
                         'Encrypted Altera/Intel MegaCore library source; readable only by Quartus with the IP licence.')
        elif head.startswith(b'XlxV'):
            typ, summ = ('Xilinx-encrypted Verilog netlist',
                         'Encrypted Xilinx (XlxV) protected netlist; readable only by the Xilinx tools.')
        elif b'\x00' not in head[:64] and sum(b > 127 for b in head) > len(head) // 4:
            typ, summ = ('Encrypted Verilog (vendor-protected IP)',
                         'Encrypted / vendor-protected Verilog source; contents cannot be read without the vendor tool.')
        else:
            typ, summ = 'Binary file with Verilog extension', ''
        return {'kind': 'binary', 'type': typ, 'summary': summ,
                'notes': ['File contains binary or encrypted data; not parsed as Verilog.'],
                'meta': [('First bytes', '`' + head[:16].hex(' ') + '`')]}
    text, trunc = core.read_text(path)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    size = len(text)
    notes = []
    if trunc:
        notes.append('File larger than 20 MB: only the first 20 MB was parsed.')

    # ---- line index
    nl = [m.start() for m in re.finditer('\n', text)]

    def line_of(pos):
        return bisect.bisect_left(nl, pos) + 1

    # ---- strip comments / attributes; collect comments
    comments = []          # (pos, raw)
    attrs = []
    parts, last = [], 0
    for m in TOKEN_RX.finditer(text):
        tok = m.group()
        if tok[0] == '"':
            continue
        parts.append(text[last:m.start()])
        if tok[0] == '(':
            attrs.append(tok)
        else:
            comments.append((m.start(), tok))
        parts.append(re.sub(r'[^\n]', ' ', tok))
        last = m.end()
    parts.append(text[last:])
    code = ''.join(parts)
    del parts

    # comment maps
    own_line = {}    # line -> text  (line holds only comment)
    trailing = {}    # line -> text  (comment after code)
    root = {}
    for pos, raw in comments:
        ln = line_of(pos)
        ls = text.rfind('\n', 0, pos) + 1
        before = code[ls:pos].strip()
        lines = _clean_comment(raw)
        t = ' '.join(x for x in lines if x).strip()
        if before:
            root[ln] = ln
            if t and not _decorative(t) and not PRAGMA.match(t):
                trailing[ln] = (trailing.get(ln, '') + ' ' + t).strip()
        elif raw.startswith("//") and len(text[ls:pos].expandtabs(4)) >= 16 and (ln - 1) in root:
            r = root[ln - 1]          # indented continuation of a trailing comment
            root[ln] = r
            if t and not _decorative(t) and not PRAGMA.match(t):
                trailing[r] = (trailing.get(r, '') + ' ' + t).strip()
        else:
            for k, t in enumerate(lines):
                own_line.setdefault(ln + k, t)

    def doc_before(ln, max_lines=12):
        got, blank = [], 0
        k = ln - 1
        while k > 0 and len(got) < max_lines:
            if k in own_line:
                got.append(own_line[k])
                k -= 1
                continue
            lstart = nl[k - 2] + 1 if k >= 2 else 0
            lend = nl[k - 1] if k - 1 < len(nl) else len(text)
            if text[lstart:lend].strip() == '' and not got and blank == 0:
                blank += 1
                k -= 1
                continue
            break
        got.reverse()
        got = [g for g in got if not _decorative(g) and not PRAGMA.match(g) and not LICENSE.search(g)
               and not CODEISH.search(g)]
        d = ' '.join(got).strip()
        return d[:500]

    # ---- preprocessor directives (record + blank out)
    defines, includes, timescale = [], [], ''
    def _dir(m):
        nonlocal timescale
        d, rest = m.group(1), m.group(2).strip()
        if d == 'define':
            mm = re.match(r'(\w+)\s*(.*)', rest)
            if mm:
                defines.append((mm.group(1), _ws(mm.group(2))[:80]))
        elif d == 'include':
            includes.append(rest.strip('"<> '))
        elif d == 'timescale':
            timescale = _ws(rest)
        elif d not in ('ifdef', 'ifndef', 'else', 'elsif', 'endif', 'undef', 'resetall', 'celldefine',
                       'endcelldefine', 'default_nettype', 'line', 'pragma', 'protect', 'endprotect',
                       'unconnected_drive', 'nounconnected_drive', 'begin_keywords', 'end_keywords'):
            return m.group(0)   # macro usage at line start: keep
        return re.sub(r'[^\n]', ' ', m.group(0))
    code = DIRECTIVE_RX.sub(_dir, code)

    head_text = text[:6000]
    hl = head_text.lower()

    # ---- generator / tool detection
    gen, wizard, wiz_module = '', '', ''
    m = re.search(r'megafunction wizard:\s*%([^%]+)%', head_text, re.I)
    if m:
        gen = 'Quartus MegaWizard'
        wizard = m.group(1).strip()
        mm = re.search(r'MODULE:\s*(\w+)', head_text)
        if mm:
            wiz_module = mm.group(1)
        else:
            mm = re.search(r'Megafunction Name\(s\):\s*\n?//\s*(\w+)', head_text)
            if mm:
                wiz_module = mm.group(1)
    elif 'written by synplify' in hl:
        gen = 'Synplify netlist'
    elif 'sch2hdl' in hl:
        gen = 'Xilinx sch2hdl'
    elif 'generated from core with identifier' in hl or 'core generator' in hl or 'coregen' in hl:
        gen = 'Xilinx CORE Generator'
    elif re.search(r'qsys|sopc builder|altera_avalon', hl):
        gen = 'Altera SOPC Builder / Qsys'
    elif 'ip compiler' in hl or 'megacore' in hl or 'ip toolbench' in hl:
        gen = 'Altera MegaCore / IP Toolbench'
    elif ext in ('vo', 'vqm') or ('quartus' in hl and 'netlist' in hl):
        gen = 'Quartus netlist'
    elif re.search(r'xilinx', hl) and re.search(r'xapp\d+|reed p\.? ?tidwell|application note', hl):
        gen = 'Xilinx reference design'
    elif 'altera corporation' in hl:
        gen = 'Altera-supplied source'
    else:
        gm = re.search(r'generated by (?:the )?([A-Za-z][^\n.,;]{2,60}?(?:wizard|compiler|generator|builder|coregen|toolbench))', head_text[:3000], re.I)
        if gm:
            gen = _ws(gm.group(1))
        elif re.search(r'(?:automatically|auto-)generated|this file (?:was|is) (?:automatically )?generated', hl[:3000]):
            gen = 'Tool-generated'
    core_id = ''
    m = re.search(r'Generated from core with identifier:\s*([\w.:\-]+)', head_text)
    if m:
        core_id = m.group(1)

    # ---- header comment -> paragraphs, meta, description
    first_code = re.search(r'\S', code)
    first_code_pos = first_code.start() if first_code else len(code)
    fd = re.search(r'^[ \t]*`(define|include)\b', text[:first_code_pos], re.M)
    if fd:
        first_code_pos = fd.start()
    hdr_lines = []
    for ln in text[:min(first_code_pos, 60000)].split('\n'):
        s0 = ln.strip()
        if s0.startswith('`'):
            hdr_lines.append(''); continue
        s0 = re.sub(r'^(//+|/\*+|\*+(?!/))', '', s0)
        s0 = re.sub(r'(\*+/|\*+)$', '', s0)
        s0 = s0.strip().strip('*').strip()
        s0 = re.sub(r'^[\s/\\_|*#=~+<>-]+(?=\w)', '', s0) if re.match(r'^[\s/\\_|]{3,}', s0) else s0
        s0 = re.sub(r'\$(?:RCSfile|Date|Revision|Author|Id|Header|Source):\s*(.*?)\s*\$', r'\1', s0)
        if PRAGMA.match(s0) or (len(s0) > 300 and s0.count('=') > 8):
            s0 = ''
        hdr_lines.append(s0)
    meta_fields, desc_lines, paras, cur = [], [], [], []
    in_desc = False
    for ln in hdr_lines:
        s = ln.strip()
        if _decorative(s):
            in_desc = in_desc and bool(s)
            if cur:
                paras.append(' '.join(cur)); cur = []
            continue
        fm = HDR_FIELD.match(s)
        if fm:
            if cur:
                paras.append(' '.join(cur)); cur = []
            key, val = fm.group(1).lower().strip(), fm.group(2).strip()
            key = re.sub(r'\s+', ' ', key)
            in_desc = key in DESC_FIELDS
            if in_desc:
                if val:
                    desc_lines.append(val)
            elif val and key in META_FIELDS and not val.startswith('$') and val not in ('-', 'N/A'):
                meta_fields.append((META_FIELDS[key], val[:120]))
            elif val and key.replace(' ', '') in ('filename', 'modulename', 'module', 'designname') and not val.startswith('$'):
                pass
            if val and not re.match(r'(?i)(revision )?0\.01 - file created', val):
                cur.append(s)
            continue
        if in_desc:
            desc_lines.append(s)
        cur.append(s)
    if cur:
        paras.append(' '.join(cur))
    paras = [p for p in paras if not LICENSE.search(p) and not BOILER.search(p) and len(p) > 2
             and not WIZ_HDR.match(p)]
    seen_meta = set()
    meta_fields = [x for x in meta_fields if not (x[0] in seen_meta or seen_meta.add(x[0]))]
    description = ' '.join(desc_lines).strip()
    short_title = ''
    if not description:
        for p in paras:
            if HDR_FIELD.match(p) or re.match(r'^\$?(Log|Revision|Id|Header|Rev\b|History|Modification|Change)', p, re.I) or re.match(r'^[\w ]{1,30}:', p):
                continue
            words = re.findall(r'[A-Za-z]{2,}', p)
            if len(words) >= 5:
                description = p
                break
            if len(words) >= 2 and not short_title:
                short_title = p
        if not description:
            description = short_title
    description = description[:700]

    # ---- design units
    end_kw = {'module': 'endmodule', 'macromodule': 'endmodule', 'interface': 'endinterface',
              'program': 'endprogram', 'package': 'endpackage', 'primitive': 'endprimitive'}

    units = []
    for m in UNIT_RX.finditer(code):
        kw, uname = m.group(1), m.group(2)
        if kw in ('interface', 'program', 'package') and not (ext in ('sv', 'svh') or re.search(r'(?<![\w$])end' + kw + r'(?![\w$])', code)):
            continue
        if units and m.start() < units[-1][4]:
            continue   # nested inside previous unit
        em = re.compile(r'(?<![\w$])' + end_kw[kw] + r'(?![\w$])').search(code, m.end())
        units.append((m.start(), m.end(), kw, uname, em.end() if em else len(code)))
    unit_names = {u[3] for u in units}
    netlist = ext in ('vqm', 'vo') or gen in ('Synplify netlist', 'Quartus netlist') or size > 1_500_000

    functions, outline = [], []
    all_inst = collections.Counter()
    clocks = collections.Counter()
    defparams_all = {}
    first_mega = None   # (type, inst, params dict)
    inst_listed = 0
    inst_total = 0
    total_ports = 0
    always_total = 0
    mod_names = []
    func_names_all = set()

    for ui, (ustart, hdr_end, kw, uname, uend) in enumerate(units):
        # skip units nested inside a previous unit's span (shouldn't happen)
        line = line_of(ustart)
        mod_names.append(uname)
        if kw == 'package':
            functions.append({'name': uname, 'kind': 'package', 'line': line,
                              'signature': f'package {uname};', 'doc': doc_before(line)})
            body_start = hdr_end
            ports, params = [], []
        else:
            # header: up to first ';' at depth 0
            i = _skip_ws(code, hdr_end)
            param_txt, port_txt, port_off = '', '', 0
            if code.startswith('import', i):
                j = code.find(';', i)
                i = _skip_ws(code, j + 1) if j >= 0 else i
            if i < len(code) and code[i] == '#':
                i = _skip_ws(code, i + 1)
                if i < len(code) and code[i] == '(':
                    j = _match_paren(code, i, uend)
                    param_txt = code[i + 1:j - 1]
                    param_off = i + 1
                    i = _skip_ws(code, j)
            if i < len(code) and code[i] == '(':
                j = _match_paren(code, i, uend)
                port_txt = code[i + 1:j - 1]
                port_off = i + 1
                i = j
            semi = code.find(';', i, uend)
            body_start = semi + 1 if semi >= 0 else i
            header_src = _ws(code[ustart:body_start])
            body = code[body_start:uend]

            # mask function/task bodies for port scanning
            ft_spans = []
            for fm in FUNC_RX.finditer(body):
                if ft_spans and fm.start() < ft_spans[-1][1]:
                    continue
                endk = 'endfunction' if fm.group(1) == 'function' else 'endtask'
                e2 = re.compile(r'(?<![\w$])' + endk + r'(?![\w$])').search(body, fm.end())
                if fm.group(1) == 'function' and re.match(r'\s*\(', body[fm.end():fm.end() + 5]):
                    continue
                ft_spans.append((fm.start(), e2.end() if e2 else len(body), fm.group(1)))
            masked = body
            if ft_spans:
                pieces, last = [], 0
                for a, b, _ in ft_spans:
                    pieces.append(body[last:a]); pieces.append(re.sub(r'[^\n]', ' ', body[a:b])); last = b
                pieces.append(body[last:])
                masked = ''.join(pieces)

            # ---- parameters
            params = []
            def add_params(txt, off, from_header):
                cur_kind = 'parameter'
                for o, item in _split_top(txt):
                    it = item.strip()
                    if not it:
                        continue
                    pm = re.match(r'(parameter|localparam)\b\s*', it)
                    if pm:
                        cur_kind = pm.group(1)
                        it = it[pm.end():]
                    if '=' not in it:
                        continue
                    lhs, rhs = it.split('=', 1)
                    nm = re.findall(r'[A-Za-z_][\w$]*', lhs)
                    if not nm:
                        continue
                    pname = nm[-1]
                    ptype = ' '.join(x for x in nm[:-1])
                    rng = re.search(r'\[[^\]]*\]', lhs)
                    tdesc = cur_kind + (' ' + ptype if ptype else '') + (' ' + _ws(rng.group()) if rng else '')
                    ln_ = line_of(off + o + item.find(pname) if pname in item else off + o)
                    params.append((pname, f'{tdesc} = {_ws(rhs)[:80]}', trailing.get(ln_, '')[:160]))
            if param_txt:
                add_params(param_txt, param_off, True)
            for pm in PARAM_RX.finditer(masked):
                add_params(pm.group(0)[:-1], body_start + pm.start(), False)

            # ---- ports
            ports = []
            port_items = _split_top(port_txt) if port_txt.strip() else []
            ansi = any(re.match(r'\s*(input|output|inout|ref)\b', it) for _, it in port_items)
            reg_names = set()
            for rm in REGDECL_RX.finditer(masked):
                for nmx in re.findall(r'(?:^|,)\s*(?:\[[^\]]*\]\s*)*([A-Za-z_][\w$]*)', re.sub(r'\[[^\]]*\]', '', rm.group(2))):
                    reg_names.add(nmx)
            if ansi:
                cdir, ctype = '', ''
                for o, it in port_items:
                    s = it.strip()
                    if not s:
                        continue
                    s2 = re.sub(r'=.*$', '', s, flags=re.S).strip()
                    words = re.findall(r'\[[^\]]*\]|[A-Za-z_][\w$.]*|\\\S+', s2)
                    if not words:
                        continue
                    pname = words[-1]
                    rest = words[:-1]
                    # trailing unpacked dims after name
                    if pname.startswith('['):
                        k = len(words) - 1
                        while k > 0 and words[k].startswith('['):
                            k -= 1
                        pname = words[k]; rest = words[:k]
                    if rest and rest[0] in ('input', 'output', 'inout', 'ref'):
                        cdir = rest[0]
                        ctype = ' '.join(_ws(w) for w in rest[1:])
                    elif rest:
                        ctype = ' '.join(_ws(w) for w in rest)
                    d = (cdir + ' ' + ctype).strip() if cdir or ctype else 'port'
                    pos = port_off + o + it.find(pname)
                    ports.append((pname, d, trailing.get(line_of(pos), '')[:160]))
            else:
                order = []
                for o, it in port_items:
                    s = it.strip()
                    mm = re.match(r'\.?\s*(\\\S+|[A-Za-z_][\w$]*)', s)
                    if mm:
                        order.append((mm.group(1), port_off + o + it.find(mm.group(1))))
                decl = {}
                for dm in DECL_RX.finditer(masked):
                    rest = dm.group(2)
                    words = re.findall(r'\[[^\]]*\]|[A-Za-z_][\w$]*|\\\S+|,', rest)
                    tparts, names = [], []
                    seen_name = False
                    for w in words:
                        if w == ',':
                            continue
                        if not seen_name and (w.startswith('[') or w in TYPE_WORDS):
                            tparts.append(_ws(w))
                        elif w.startswith('['):
                            continue
                        else:
                            seen_name = True
                            names.append(w)
                    ln_ = line_of(body_start + dm.start())
                    for nmx in names:
                        decl[nmx] = (dm.group(1) + (' ' + ' '.join(tparts) if tparts else ''), ln_)
                for nmx, pos in order:
                    if nmx in decl:
                        d, ln_ = decl[nmx]
                        if d.startswith('output') and 'reg' not in d and nmx in reg_names:
                            d = d.replace('output', 'output reg', 1)
                        note = trailing.get(ln_, '') or trailing.get(line_of(pos), '')
                    else:
                        d, note = 'port (undeclared)', trailing.get(line_of(pos), '')
                    ports.append((nmx, d, note[:160]))
                if not order and decl and kw == 'primitive':
                    for nmx, (d, ln_) in decl.items():
                        ports.append((nmx, d, trailing.get(ln_, '')[:160]))
            for k, p in enumerate(ports):
                if p[1].startswith('output') and 'reg' not in p[1] and p[0] in reg_names:
                    ports[k] = (p[0], p[1].replace('output', 'output reg', 1), p[2])
            total_ports += len(ports)

            # ---- instances
            calls, inst_list = [], []
            i_cnt = collections.Counter()
            pos = 0
            blen = len(masked)
            while True:
                m2 = INST_HEAD.search(masked, pos)
                if not m2:
                    break
                typ = m2.group(1)
                pos = m2.end()
                if typ in KEYWORDS and typ not in GATES:
                    continue
                # context: previous significant char/token
                k = m2.start() - 1
                while k >= 0 and masked[k] in ' \t\r\n':
                    k -= 1
                ok = k < 0 or masked[k] in ';)'
                if not ok:
                    w = re.search(r'([A-Za-z_][\w$]*)$', masked[max(0, k - 30):k + 1])
                    if w and w.group(1) in ('begin', 'end', 'generate', 'else', 'endcase', 'endgenerate',
                                            'endfunction', 'endtask', 'join'):
                        ok = True
                    elif w:
                        k2 = k - len(w.group(1))
                        while k2 >= 0 and masked[k2] in ' \t\r\n':
                            k2 -= 1
                        if k2 >= 0 and masked[k2] == ':':
                            ok = True
                    elif masked[k] == ':':
                        ok = True
                if not ok:
                    continue
                i = pos
                ovr = None
                if i < blen and masked[i] == '#':
                    i = _skip_ws(masked, i + 1)
                    if i < blen and masked[i] == '(':
                        j = _match_paren(masked, i)
                        ovr = masked[i + 1:j - 1]
                        i = _skip_ws(masked, j)
                    else:
                        mm = re.match(r'[\w.]+', masked[i:i + 40])
                        if not mm:
                            continue
                        i = _skip_ws(masked, i + mm.end())
                mi = IDENT.match(masked, i)
                if not mi:
                    continue
                iname = mi.group()
                if iname in KEYWORDS:
                    continue
                i = _skip_ws(masked, mi.end())
                if i < blen and masked[i] == '[':
                    j = masked.find(']', i)
                    if j < 0:
                        continue
                    i = _skip_ws(masked, j + 1)
                if i >= blen or masked[i] != '(':
                    continue
                j = _match_paren(masked, i)
                pos = j
                i_cnt[typ] += 1
                inst_total += 1
                if typ not in calls:
                    calls.append(typ)
                if len(inst_list) < 5000:
                    inst_list.append((iname, typ, body_start + m2.start()))
                if ovr is not None and first_mega is None and _is_ip(typ):
                    first_mega = (typ, iname, _named_args(ovr))
            all_inst.update(i_cnt)

            # defparams
            dp = {}
            if not netlist or size < 3_000_000:
                for dm in DEFPARAM_RX.finditer(masked):
                    for pm in re.finditer(r'(\\\S+|[\w$\[\].]+)\s*\.\s*([A-Za-z_]\w*)\s*=\s*("[^"]*"|[^,;\s]+)', dm.group(1)):
                        dp.setdefault(pm.group(1).strip(), {}).setdefault(pm.group(2).lower(), pm.group(3).strip('"'))
            for iname, typ, _p in inst_list:
                if iname in dp:
                    defparams_all.setdefault((typ, iname), {}).update(dp[iname])
                    if first_mega is None and _is_ip(typ):
                        first_mega = (typ, iname, dp[iname])

            sig = header_src
            if len(sig) > 6000 or len(ports) > 80:
                sig = f'{kw} {uname} ' + ('#(...) ' if param_txt else '') + f'(/* {len(ports)} ports */);'
            else:
                sig = _pretty_header(code[ustart:body_start])
            fdoc = doc_before(line)
            if not fdoc and ui == 0:
                fdoc = description[:300]
            entry = {'name': uname, 'kind': kw, 'line': line, 'signature': sig, 'doc': fdoc,
                     'params': (ports + params)[:MAX_PARAMS], 'calls': calls}
            if len(ports) + len(params) > MAX_PARAMS:
                notes.append(f'{uname}: {len(ports) + len(params)} ports/parameters; table capped at {MAX_PARAMS}.')
            if len(functions) < MAX_FUNCS:
                functions.append(entry)

            # ---- outline for this unit
            ol = []
            if inst_list:
                many = netlist or len(inst_list) > 80
                prim_heavy = len(inst_list) > 30 and any(_is_prim(t) for t in i_cnt)
                if many:
                    ol.append(', '.join(f'`{t}` × {c:,}' for t, c in i_cnt.most_common(12))
                              + (f', … {len(i_cnt) - 12} more types' if len(i_cnt) > 12 else ''))
                elif prim_heavy:
                    ol.append('primitives: ' + ', '.join(f'`{t}` × {c:,}' for t, c in i_cnt.most_common() if _is_prim(t)))
                for iname, typ, _p in inst_list:
                    if inst_listed >= MAX_INST_OUTLINE:
                        break
                    if many and typ not in unit_names:
                        continue
                    if prim_heavy and not many and _is_prim(typ):
                        continue
                    ol.append(f'`{iname}` : `{typ}`')
                    inst_listed += 1
            gen_labels = re.findall(r'(?<![\w$])begin\s*:\s*([A-Za-z_][\w$]*)', masked) if 'generate' in masked else []
            n_gen = len(re.findall(r'(?<![\w$])generate(?![\w$])', masked))
            if n_gen:
                ol.append(f'generate regions: {n_gen}' + (f" (labels: {', '.join(gen_labels[:20])})" if gen_labels else ''))
            assigns = len(re.findall(r'(?<![\w$])assign(?![\w$])', masked))
            if assigns or n_gen:
                extra = []
                if assigns:
                    extra.append(f'{assigns} continuous assign{"s" if assigns != 1 else ""}')
                if n_gen:
                    extra.append(f'{n_gen} generate region{"s" if n_gen != 1 else ""}')
                if i_cnt:
                    extra.append(f'{sum(i_cnt.values()):,} instance{"s" if sum(i_cnt.values()) != 1 else ""}')
                entry['signature'] = entry['signature'] + '\n// body: ' + ', '.join(extra)
            if ol:
                outline.append({'heading': f'{kw} {uname} (line {line})'})
                outline.extend(ol)

            # ---- functions / tasks
            for a, b, fk in ft_spans:
                if len(functions) >= MAX_FUNCS:
                    break
                fe = _parse_func(body[a:b], fk, body_start + a, line_of, trailing, doc_before)
                if fe:
                    func_names_all.add(fe['name'])
                    functions.append(fe)

            # ---- always / initial blocks
            ord_ = 0
            for am in ALWAYS_RX.finditer(masked):
                if len(functions) >= MAX_FUNCS:
                    notes.append(f'Function/block list capped at {MAX_FUNCS} entries.')
                    break
                akw = am.group(1)
                i = _skip_ws(masked, am.end())
                sens = ''
                if i < blen and masked[i] == '@':
                    j = _skip_ws(masked, i + 1)
                    if j < blen and masked[j] == '(':
                        k = _match_paren(masked, j)
                        sens = '@' + _ws(masked[j:k])
                        i = _skip_ws(masked, k)
                    else:
                        mm = re.match(r'\*|[\w$.]+', masked[j:j + 60])
                        if mm:
                            sens = '@' + mm.group()
                            i = _skip_ws(masked, j + mm.end())
                elif i < blen and masked[i] == '#':
                    mm = re.match(r'#\s*[\w.]+', masked[i:i + 40])
                    if mm:
                        sens = _ws(mm.group())
                        i = _skip_ws(masked, i + mm.end())
                # statement extent
                send = _stmt_end(masked, i)
                stmt = masked[i:send]
                label = ''
                lm = re.match(r'begin\s*:\s*([A-Za-z_][\w$]*)', stmt)
                if lm:
                    label = lm.group(1)
                ord_ += 1
                always_total += 1
                for ck in re.findall(r'(?:posedge|negedge)\s+([A-Za-z_][\w$.]*)', sens):
                    clocks[ck] += 1
                aline = line_of(body_start + am.start())
                hdr = _ws(f'{akw} {sens}')
                if len(hdr) > 90:
                    hdr = hdr[:87] + '…'
                nm = label if label else f'{hdr} #{ord_}'
                sigtxt = _ws(f'{akw} {sens}') + (f' begin : {label}' if label else '')
                doc = doc_before(aline)
                tr = trailing.get(aline, '')
                if tr and tr not in doc:
                    doc = (doc + ' ' + tr).strip()
                targets = _assigned(stmt)
                calls_b = [f for f in func_names_all if re.search(r'(?<![\w$])' + re.escape(f) + r'\s*\(', stmt)][:20] if func_names_all else []
                desc = doc
                kindtxt = {'always': 'always', 'always_ff': 'always_ff', 'always_comb': 'always_comb',
                           'always_latch': 'always_latch', 'initial': 'initial', 'final': 'final'}[akw]
                clk_txt = re.findall(r'(posedge|negedge)\s+([A-Za-z_][\w$.]*)', sens)
                if targets:
                    desc = (desc + ' ' if desc else '') + '→ ' + ', '.join(targets[:25]) + (' …' if len(targets) > 25 else '')
                fe = {'name': nm, 'kind': kindtxt, 'line': aline, 'signature': sigtxt, 'doc': desc[:700]}
                if calls_b:
                    fe['calls'] = calls_b
                if label:
                    fe['signature'] = sigtxt
                functions.append(fe)

    # ---- functions / tasks outside any module (include files)
    spans = [(u[0], u[4]) for u in units]
    for fm in FUNC_RX.finditer(code):
        if any(a <= fm.start() < b for a, b in spans):
            continue
        endk = 'endfunction' if fm.group(1) == 'function' else 'endtask'
        e2 = re.compile(r'(?<![\w$])' + endk + r'(?![\w$])').search(code, fm.end())
        b = e2.end() if e2 else len(code)
        spans.append((fm.start(), b))
        fe = _parse_func(code[fm.start():b], fm.group(1), fm.start(), line_of, trailing, doc_before)
        if fe and len(functions) < MAX_FUNCS:
            func_names_all.add(fe['name'])
            functions.append(fe)

    # ---- top-level instances outside modules (.veo templates)
    template = None
    tmpl_src = ''
    if not units:
        mt = re.search(r'(?<![\w$`.])([A-Za-z_][\w$]*)\s+(?:#\s*\([^;]*?\)\s*)?(?:([A-Za-z_][\w$]*)\s*)?\(\s*\.', code)
        if mt and mt.group(1) not in KEYWORDS:
            p0 = code.rfind('(', mt.start(), mt.end())
            j = _match_paren(code, p0)
            ports = []
            for pm in re.finditer(r'\.\s*([A-Za-z_][\w$]*)\s*\(([^()]*)\)', code[p0:j]):
                pl = line_of(p0 + pm.start())
                note = trailing.get(pl, '')
                dm = re.match(r'(input|output|inout)\s*(\[[^\]]*\])?\s*', note)
                if dm:
                    d = dm.group(1) + (' ' + _ws(dm.group(2)).replace(' ', '') if dm.group(2) else '')
                    ports.append((pm.group(1), d, 'connected to `' + _ws(pm.group(2)) + '`' if pm.group(2).strip() else 'unconnected'))
                else:
                    conn = _ws(pm.group(2))
                    ports.append((pm.group(1), 'port', ((f'connected to `{conn}`' if conn else 'unconnected') + ('; ' + note if note else ''))[:160]))
            template = mt.group(1)
            if ext == 'veo' or gen == 'Xilinx CORE Generator':
                tsrc = 'Xilinx CORE Generator'
            elif 'ipexpress' in hl or 'lattice' in hl:
                tsrc = 'Lattice IPexpress'
            elif name.lower().endswith('_inst.v') or 'altera' in hl or template.startswith('alt'):
                tsrc = 'Quartus MegaWizard'
            else:
                tsrc = ''
            tmpl_src = tsrc
            functions.insert(0, {'name': template, 'kind': 'instance template', 'line': line_of(mt.start()),
                                 'signature': text[mt.start():j + 1].strip()[:4000],
                                 'doc': (f'Core {core_id}.' if core_id else ''),
                                 'params': ports})
            mod_names.append(template)

    functions.sort(key=lambda f: f.get('line') or 0)

    # ---- megafunction / IP parameters
    mega_params = {}
    mega_type = ''
    if first_mega:
        mega_type = first_mega[0]
        mega_params.update({k.lower(): str(v).strip('"') for k, v in first_mega[2].items()})
    if gen == 'Quartus MegaWizard' or mega_type:
        for mm in re.finditer(r'Retrieval info:\s*CONSTANT:\s*(\w+)\s+\w+\s+"([^"]*)"', text):
            mega_params.setdefault(mm.group(1).lower(), mm.group(2))
        for mm in re.finditer(r'Retrieval info:\s*PRIVATE:\s*(\w+)\s+\w+\s+"([^"]*)"', text):
            mega_params.setdefault('private:' + mm.group(1).lower(), mm.group(2))
        if wiz_module:
            lm = re.search(r'^//' + re.escape(wiz_module) + r' (.*)$', text, re.M)
            if lm:
                for mm in re.finditer(r'(\w+)=("[^"]*"|\S+)', lm.group(1)):
                    mega_params.setdefault(mm.group(1).lower(), mm.group(2).strip('"'))
    pdefs = {}
    for f in functions:
        for p_ in f.get('params') or []:
            if str(p_[1]).startswith(('parameter', 'localparam')) and ' = ' in str(p_[1]):
                pdefs.setdefault(p_[0], str(p_[1]).split(' = ', 1)[1].strip().strip('"'))
    resolved = False
    for k_, v_ in list(mega_params.items()):
        if v_ in pdefs:
            mega_params[k_] = pdefs[v_]
            resolved = True
    ip_name = wiz_module or mega_type
    ip_desc = _describe_ip(ip_name, mega_params) if (ip_name or mega_params) else ''
    if ip_desc and resolved:
        ip_desc += ' (using module parameter defaults)'

    show_ip = gen == 'Quartus MegaWizard' or bool(mega_type and inst_total <= 4)
    if not show_ip:
        ip_desc = ''
    if ip_desc and ip_name:
        for f in functions:
            if f.get('kind') == 'module' and (ip_name in (f.get('calls') or []) or mega_type in (f.get('calls') or [])):
                if not f.get('doc') or f['doc'] == description[:300]:
                    f['doc'] = f'Wrapper around {mega_type or ip_name}: {ip_desc}.'
    # ---- type / summary
    real_mods_pre = [f for f in functions if f.get('kind') in ('module', 'macromodule', 'program')]
    is_sv = ext in ('sv', 'svh')
    lang = 'SystemVerilog' if is_sv else 'Verilog'
    if template:
        typ = ((tmpl_src + ' ') if tmpl_src else '') + 'instantiation template (Verilog)'
    elif ext == 'vf':
        typ = 'Xilinx schematic-generated Verilog netlist (sch2hdl)'
    elif ext == 'vqm':
        typ = 'VQM post-synthesis Verilog netlist' + (' (Synplify)' if gen == 'Synplify netlist' else ' (Quartus)')
    elif ext == 'vo':
        typ = 'Quartus Verilog output netlist'
    elif gen == 'Quartus MegaWizard':
        typ = f'Quartus MegaWizard {ip_name or wizard} wrapper (Verilog)'
    elif gen == 'Synplify netlist':
        typ = 'Synplify Verilog netlist'
    elif netlist:
        typ = f'{lang} gate-level netlist' + (f' ({gen})' if gen else '')
    elif gen == 'Quartus netlist':
        typ = 'Quartus Verilog netlist'
    elif gen == 'Xilinx CORE Generator':
        typ = 'Xilinx CORE Generator Verilog wrapper'
    elif gen:
        typ = f'{lang} HDL source ({gen})'
    else:
        typ = f'{lang} HDL source'
        if ext in ('vh', 'svh'):
            typ = f'{lang} header / include file'
        elif ext == 'vt' or (real_mods_pre and all(not any(not str(p[1]).startswith(('parameter', 'localparam')) for p in f.get('params', [])) for f in real_mods_pre[:1]) and any(f.get('kind') == 'initial' for f in functions)):
            typ = f'{lang} test bench'
    if ext in ('v~', 'v~~', 'v#'):
        typ += ' — editor backup copy'

    real_mods = [f for f in functions if f.get('kind') in ('module', 'macromodule', 'interface', 'program', 'primitive')]
    structure = ''
    if real_mods:
        called = set()
        for f in real_mods:
            called.update(f.get('calls') or [])
        roots = [f for f in real_mods if f['name'] not in called] or real_mods
        top = max(roots, key=lambda f: (len(f.get('calls') or []), len(f.get('params') or []), f.get('line', 0)))
        np_ = sum(1 for p in top.get('params', []) if not str(p[1]).startswith(('parameter', 'localparam')))
        tb = np_ == 0 and any(f.get('kind') == 'initial' for f in functions)
        bits = [f'{np_} port' + ('s' if np_ != 1 else '') if np_ else ('no ports (test bench)' if tb else 'no ports')]
        if always_total:
            bits.append(f'{always_total} always/initial block' + ('s' if always_total != 1 else ''))
        nf = sum(1 for f in functions if f.get('kind') in ('function', 'task'))
        if nf:
            bits.append(f'{nf} function/task' + ('s' if nf != 1 else ''))
        if inst_total:
            types = [t for t, _ in sorted(all_inst.most_common(), key=lambda tc: (_is_prim(tc[0]), -tc[1]))[:8]]
            bits.append(f'{inst_total:,} instance' + ('s' if inst_total != 1 else '') + ' of ' + ', '.join(types)
                        + (' …' if len(all_inst) > 8 else ''))
        if len(real_mods) > 1:
            structure = (f'Defines {len(real_mods)} modules ('
                         + ', '.join(f['name'] for f in real_mods[:8]) + (' …' if len(real_mods) > 8 else '')
                         + f'); top-level `{top["name"]}`: ' + '; '.join(bits) + '.')
        else:
            structure = f'Defines module `{top["name"]}`: ' + '; '.join(bits) + '.'

    summ = ''
    if gen == 'Quartus MegaWizard':
        summ = f'Quartus MegaWizard {ip_name or wizard} wrapper' + (f': {ip_desc}' if ip_desc else '') + '.'
        if real_mods:
            summ += f' Wrapper module `{real_mods[-1]["name"]}`.'
    elif template:
        summ = (((tmpl_src + ' ') if tmpl_src else '') + f'instantiation template for `{template}`'
                + f' ({len(functions[0].get("params") or [])} port connections)'
                + (f' ({core_id})' if core_id else '') + '.')
        if description and not description.lower().startswith('generated from core'):
            summ += ' ' + description
        else:
            dpar = next((p for p in paras if len(p) > 60 and not p.lower().startswith(('generated from', 'interfaces'))), '')
            if dpar:
                summ += ' ' + dpar[:500]
    elif ext == 'vf':
        dn = re.search(r'Design Name:\s*(\S+)', head_text)
        dv = re.search(r'Device:\s*(\S+)', head_text)
        summ = ('Verilog netlist translated by Xilinx sch2hdl from ECS schematic'
                + (f' `{dn.group(1)}`' if dn else '') + (f' ({dv.group(1)})' if dv else '') + '. ' + structure)
    elif netlist:
        summ = (typ + (f', generated by {gen}' if gen and gen.split()[0] not in typ else '') + '. ' + structure)
    else:
        if description:
            summ = description + (' ' if description.endswith('.') else '. ') + structure
        else:
            summ = structure
        if ip_desc and mega_type:
            summ += f' Configured {mega_type}: {ip_desc}.'
    summ = summ.strip()

    # ---- meta
    meta = []
    if gen:
        meta.append(('Generator', gen + (f' ({wizard})' if wizard else '')))
    hm = re.search(r'(\d+\.\d+(?:\.\d+)? Build \d+[^\n]*)', head_text)
    if not hm:
        hm = re.search(r'Product Version\s+"?([^"\n]+)', head_text)
    if hm:
        meta.append(('Tool version', _ws(hm.group(1)).strip('"')[:80]))
    if core_id:
        meta.append(('Core', core_id))
    fam = mega_params.get('intended_device_family') or mega_params.get('device_family')
    if fam:
        meta.append(('Device family', fam))
    meta.extend(meta_fields[:8])
    meta.append(('Lines', f'{len(nl) + 1:,}'))
    if real_mods:
        meta.append(('Modules', len(real_mods)))
    if always_total:
        meta.append(('Always/initial blocks', always_total))
    if inst_total:
        meta.append(('Instances', f'{inst_total:,} ({len(all_inst)} distinct types)'))
    if clocks:
        meta.append(('Clocks (edge-sensitive)', ', '.join(f'`{c}`' for c, _ in clocks.most_common(8))))
    if timescale:
        meta.append(('Timescale', f'`{timescale}`'))
    if ip_desc:
        meta.append(('IP configuration', ip_desc))
    if mega_params and show_ip:
        keep = [(k, v) for k, v in mega_params.items() if not k.startswith('private:') and not k.startswith('port_')
                and k not in ('lpm_hint',) and (gen == 'Quartus MegaWizard' or not re.match(
                    r'(c\d+_|[mn]\d*_|vco_|charge_pump|loop_filter|lut_mask|sum_lutc|.*_(high|low|initial|mode|ph)$)', k))][:24]
        keep = [(k, v if len(v) <= 48 else v[:45] + '…') for k, v in keep if not re.match(r'initp?_[0-9a-f]{2}$', k)]
        if keep:
            meta.append(('IP parameters', ', '.join(f'{k}={v}' for k, v in keep)))
    if includes:
        meta.append(('Includes', ', '.join(f'`{x}`' for x in includes[:20])))

    if defines:
        outline.append({'heading': f'`define macros ({len(defines)})'})
        for dn_, dv_ in defines[:100]:
            outline.append(f'`{dn_}` = `{dv_}`' if dv_ else f'`{dn_}`')
        if len(defines) > 100:
            outline.append(f'… {len(defines) - 100} more')
    if netlist and all_inst:
        outline.append({'heading': 'Cell / primitive usage (whole file)'})
        for t, c in all_inst.most_common(60):
            outline.append(f'`{t}` × {c:,}')
    if inst_total > inst_listed and inst_listed >= MAX_INST_OUTLINE:
        notes.append(f'Instance list truncated: {inst_listed} of {inst_total:,} instances shown.')
    if netlist and inst_total > 60:
        notes.append(f'Netlist with {inst_total:,} cell instances: per-instance listing omitted; cell types counted instead.')
    if not units and not template:
        if functions:
            notes.append('No module declarations: function/task include file.')
            if typ.endswith('HDL source'):
                typ = f'{lang} include file (functions/tasks)'
            summ = ('Defines ' + ', '.join(f"{f['kind']} `{f['name']}`" for f in functions[:10]) + '.')
            if description:
                summ = description.rstrip(' .;') + '. ' + summ
        else:
            notes.append('No module declarations found (fragment, include file or non-Verilog content).')

    # ---- keywords
    kw = []
    if ip_name and show_ip:
        kw.append(ip_name)
    kw.extend(mod_names[:5])
    for t, _ in sorted(all_inst.most_common(), key=lambda tc: (_is_prim(tc[0]), -tc[1]))[:8]:
        if not _is_prim(t) and t not in unit_names:
            kw.append(t)
    for c, _ in clocks.most_common(3):
        kw.append(c)
    if fam:
        kw.append(fam)
    seen = set()
    kw = [k for k in kw if not (k.lower() in seen or seen.add(k.lower()))][:12]

    res = {'kind': 'source', 'type': typ, 'summary': summ, 'keywords': kw, 'meta': meta,
           'functions': functions, 'outline': outline, 'code_lang': 'systemverilog' if is_sv else 'verilog',
           'paragraphs': paras[:60]}
    if real_mods and len(real_mods) == 1:
        res['title'] = real_mods[0]['name']
    if notes:
        res['notes'] = list(dict.fromkeys(notes))[:12]
    return res


# ------------------------------------------------------------------ sub-parsers
def _pretty_header(src):
    src = '\n'.join(ln.rstrip() for ln in src.split('\n') if ln.strip())
    return src.strip()


def _named_args(s):
    out = {}
    for mm in re.finditer(r'\.\s*([A-Za-z_][\w$]*)\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)', s):
        out[mm.group(1).lower()] = _ws(mm.group(2)).strip('"')
    return out


IP_RX = re.compile(r'^(alt\w+|lpm_\w+|dcfifo\w*|scfifo|sld_\w+|(?:cyclone|stratix|arria)\w*_pll|'
                   r'DCM\w*|PLL_\w+|MMCM\w*|BUFG\w*|IBUF\w*|OBUF\w*|IBUFDS\w*|OBUFDS\w*|RAMB\w+|FIFO\d+\w*|'
                   r'GTP\w+|GTX\w+|ODDR\w*|IDDR\w*|ISERDES\w*|OSERDES\w*|SRL\w+|DSP48\w*|BUFIO\w*|BUFR|'
                   r'IODELAY\w*|ICAP\w*|STARTUP\w*)$')


PRIM_RX = re.compile(r'^(GND|VCC|BUF\w*|INV\w*|IBUF\w*|OBUF\w*|IOBUF\w*|FD\w*|LD\w*|(?:AND|OR|NAND|NOR|XOR|XNOR)\d\w*|'
                     r'MUX\w*|M2_1\w*|M4_1\w*|LUT\d\w*|PULL\w+|KEEPER|CB\d\w*|XORCY\w*|MULT_AND|SRL\w*|'
                     r'dffeas|dffe|dff|\w*lcell\w*|\w*_io(?:ibuf|obuf)?|\w*_io_\w+|\w*_ff|and|or|not|buf|xor|nand|nor|xnor)$')


def _is_prim(t):
    return bool(PRIM_RX.match(t))


def _is_ip(t):
    return bool(IP_RX.match(t))


def _describe_ip(name, p):
    n = (name or p.get('lpm_type', '') or '').lower()
    fam = p.get('intended_device_family', '')
    try:
        if 'pll' in n and 'reconfig' not in n and 'inclk0_input_frequency' in p:
            ps = _num(p['inclk0_input_frequency'])
            fin = 1e6 / ps if ps else None
            outs = []
            for k in range(10):
                mul = _num(p.get(f'clk{k}_multiply_by', ''))
                div = _num(p.get(f'clk{k}_divide_by', ''))
                used = p.get(f'port_clk{k}', '').upper()
                if mul is None or div is None or used == 'PORT_UNUSED':
                    eff = p.get(f'private:eff_output_freq_value{k}')
                    if eff and used == 'PORT_USED':
                        outs.append(f'c{k} {_mhz(float(eff))}')
                    continue
                if fin and div:
                    outs.append(f'c{k} {_mhz(fin * mul / div)} (×{mul:g}/{div:g})')
            if fin:
                return f'{_mhz(fin)} in' + (', out ' + ', '.join(outs) if outs else '') + (f' [{fam}]' if fam else '')
        if n.startswith(('dcm', 'pll_', 'mmcm')) and 'clkin_period' in p:
            per = _num(p['clkin_period'])
            fin = 1000.0 / per if per else None
            bits = [f'{_mhz(fin)} in'] if fin else []
            if 'clkfx_multiply' in p and 'clkfx_divide' in p:
                m_, d_ = _num(p['clkfx_multiply']), _num(p['clkfx_divide'])
                if fin and m_ and d_:
                    bits.append(f'CLKFX {_mhz(fin * m_ / d_)} (×{m_:g}/{d_:g})')
            mult = _num(p.get('clkfbout_mult', p.get('clkfbout_mult_f', '')))
            dv = _num(p.get('divclk_divide', '1')) or 1
            if fin and mult:
                for k in range(7):
                    od = _num(p.get(f'clkout{k}_divide', p.get(f'clkout{k}_divide_f', '')))
                    if od:
                        bits.append(f'CLKOUT{k} {_mhz(fin * mult / dv / od)}')
            if bits:
                return ', '.join(bits)
        if 'fifo' in n:
            w = p.get('lpm_width'); d = p.get('lpm_numwords')
            kind = 'dual-clock FIFO' if 'dc' in n or p.get('private:clock') == '4' else 'single-clock FIFO'
            if n.startswith('scfifo'):
                kind = 'single-clock FIFO'
            if w and d:
                s = f'{kind}, {w} bit{"s" if str(w) != "1" else ""} × {d} words'
                if p.get('lpm_showahead', '').upper() == 'ON':
                    s += ', show-ahead'
                return s + (f' [{fam}]' if fam else '')
        if any(x in n for x in ('syncram', 'dpram', 'lpm_rom', 'lpm_ram', 'altsyncram', 'rom', 'ram')):
            mode = p.get('operation_mode', '')
            wa, na = p.get('width_a') or p.get('lpm_width'), p.get('numwords_a') or p.get('lpm_numwords')
            s = (mode.replace('_', ' ').lower().replace('rom', 'ROM') + ' ' if mode else '') + 'memory'
            if wa and na:
                s += f', {wa} bit{"s" if str(wa) != "1" else ""} × {na} words'
            wb, nb = p.get('width_b'), p.get('numwords_b')
            if wb and nb and (wb, nb) != (wa, na):
                s += f' (port B {wb} × {nb})'
            init = p.get('init_file') or p.get('lpm_file')
            if init and init.upper() != 'UNUSED':
                s += f', init file {init}'
            if s == 'memory':
                return ''
            return s + (f' [{fam}]' if fam else '')
        fs = f' [{fam}]' if fam else ''
        rep = p.get('lpm_representation', '').lower()
        if 'mult' in n and p.get('lpm_widtha'):
            s = f"{rep + ' ' if rep else ''}multiplier {p['lpm_widtha']} × {p.get('lpm_widthb', '?')} → {p.get('lpm_widthp', '?')} bits"
            if p.get('lpm_pipeline') and p['lpm_pipeline'] != '0':
                s += f", {p['lpm_pipeline']}-stage pipeline"
            return s + fs
        if 'counter' in n and p.get('lpm_width'):
            s = f"{p['lpm_width']}-bit {p.get('lpm_direction', '').lower() + ' ' if p.get('lpm_direction') else ''}counter"
            if p.get('lpm_modulus'):
                s += f", modulus {p['lpm_modulus']}"
            return s + fs
        if 'add_sub' in n and p.get('lpm_width'):
            d = p.get('lpm_direction', '').upper()
            op = {'ADD': 'adder', 'SUB': 'subtractor'}.get(d, 'adder/subtractor')
            return f"{p['lpm_width']}-bit {rep + ' ' if rep else ''}{op}" + fs
        if 'clkctrl' in n:
            return f"global clock control buffer{', ' + p['clock_type'] if p.get('clock_type') else ''}" + fs
        if 'accumulate' in n and p.get('width_in'):
            return f"{rep + ' ' if rep else ''}accumulator {p['width_in']} → {p.get('width_out', '?')} bits" + fs
        keys = ['lpm_width', 'lpm_widtha', 'lpm_widthb', 'lpm_widthp', 'lpm_widthd', 'lpm_widthn', 'lpm_widths',
                'lpm_size', 'lpm_direction', 'lpm_representation', 'lpm_modulus', 'lpm_pipeline',
                'number_of_channels', 'deserialization_factor', 'data_rate', 'width', 'width_a', 'width_b',
                'number_of_taps', 'tap_distance', 'lpm_shifttype']
        bits = [f'{k}={p[k]}' for k in keys if k in p]
        if bits:
            return ', '.join(bits[:8]) + (f' [{fam}]' if fam else '')
        if fam:
            return f'[{fam}]'
    except Exception:
        return ''
    return ''


def _stmt_end(code, i, cap=400_000):
    """End index of the statement starting at i (begin/end, case/endcase aware)."""
    depth = 0
    n = min(len(code), i + cap)
    pos = i
    while True:
        m = BLOCK_TOK.search(code, pos, n)
        if not m:
            return n
        t = m.group()
        pos = m.end()
        if t == '(':
            pos = _match_paren(code, m.start(), n)
            continue
        if t in ('begin', 'case', 'casex', 'casez', 'randcase', 'fork'):
            depth += 1
            continue
        if t in ('end', 'endcase', 'join', 'join_any', 'join_none'):
            depth -= 1
        if depth <= 0:
            k = _skip_ws(code, pos)
            if t == 'end' or t == ';' or t == 'endcase':
                if re.match(r'else(?![\w$])', code[k:k + 5]):
                    pos = k + 4
                    depth = 0
                    continue
            if depth < 0:
                return pos
            if t == ';' and depth == 0:
                return pos
            if t in ('end', 'endcase', 'join', 'join_any', 'join_none') and depth == 0:
                return pos


ASSIGN_RX = re.compile(r'(?:^|[;)]|(?<![\w$])(?:begin|else|end|default)|:)\s*(?:#\s*[\d.]+\s*)?([A-Za-z_][\w$.]*)\s*(?:\[[^\]]*\]\s*)*(?:<=|=(?!=))')
CONCAT_ASSIGN = re.compile(r'(?:^|[;)]|(?<![\w$])(?:begin|else|end)|:)\s*\{([^{}]*)\}\s*(?:<=|=(?!=))')


def _assigned(stmt):
    out = []
    s = stmt[:200_000]
    for m in ASSIGN_RX.finditer(s):
        t = m.group(1)
        if t in KEYWORDS or t in out:
            continue
        out.append(t)
    for m in CONCAT_ASSIGN.finditer(s):
        for t in re.findall(r'[A-Za-z_][\w$]*', re.sub(r'\[[^\]]*\]', '', m.group(1))):
            if t not in out and t not in KEYWORDS:
                out.append(t)
    # drop for-loop variables
    loopv = set(re.findall(r'for\s*\(\s*(?:int\s+|integer\s+|genvar\s+)?([A-Za-z_]\w*)\s*=', s))
    return [t for t in out if t not in loopv]


def _parse_func(src, fk, abspos, line_of, trailing, doc_before):
    endk = 'endfunction' if fk == 'function' else 'endtask'
    m = re.match(r'(function|task)\s+((?:automatic|static)\s+)?', src)
    if not m:
        return None
    i = m.end()
    semi = src.find(';', i)
    if semi < 0:
        return None
    hdr = src[i:semi]
    args_txt = ''
    if '(' in hdr:
        p0 = hdr.find('(')
        p1 = _match_paren(hdr, p0)
        args_txt = hdr[p0 + 1:p1 - 1]
        pre = hdr[:p0]
    else:
        pre = hdr
    words = re.findall(r'\[[^\]]*\]|[A-Za-z_][\w$:.]*', pre)
    if not words:
        return None
    name = words[-1]
    rtype = ' '.join(_ws(w) for w in words[:-1])
    if '::' in name:
        name = name.split('::')[-1]
    params = []
    if args_txt.strip():
        cdir, ctype = 'input', ''
        for o, it in _split_top(args_txt):
            w = re.findall(r'\[[^\]]*\]|[A-Za-z_][\w$]*', re.sub(r'=.*$', '', it, flags=re.S))
            if not w:
                continue
            nm = w[-1]
            rest = w[:-1]
            if rest and rest[0] in ('input', 'output', 'inout', 'ref'):
                cdir = rest[0]; ctype = ' '.join(_ws(x) for x in rest[1:])
            elif rest:
                ctype = ' '.join(_ws(x) for x in rest)
            params.append((nm, (cdir + ' ' + ctype).strip(), trailing.get(line_of(abspos + i + hdr.find('(') + 1 + o), '')[:160]))
    body = src[semi + 1:]
    for dm in re.finditer(r'(?<![\w$])(input|output|inout)\b([^;]*);', body):
        ws_ = re.findall(r'\[[^\]]*\]|[A-Za-z_][\w$]*', dm.group(2))
        t, names = [], []
        for w in ws_:
            if not names and (w.startswith('[') or w in TYPE_WORDS):
                t.append(_ws(w))
            elif not w.startswith('['):
                names.append(w)
        ln_ = line_of(abspos + semi + 1 + dm.start())
        for nm in names:
            params.append((nm, (dm.group(1) + ' ' + ' '.join(t)).strip(), trailing.get(ln_, '')[:160]))
    line = line_of(abspos)
    sig = _ws(src[:semi + 1])
    if len(sig) > 400:
        sig = sig[:400] + ' …'
    doc = doc_before(line) or trailing.get(line, '')
    fe = {'name': name, 'kind': fk, 'line': line, 'signature': sig, 'doc': doc, 'params': params[:80]}
    if fk == 'function':
        fe['returns'] = rtype or '1-bit (implicit)'
    targets = [t for t in _assigned(body) if t != name][:20] if fk == 'task' else []
    if targets:
        fe['doc'] = (doc + ' ' if doc else '') + '→ ' + ', '.join(targets)
    return fe
