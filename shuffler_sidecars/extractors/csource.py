"""C-like and high-level source extractor: C/C++ (incl. preprocessed .i), Java, C#,
JavaScript, IDL, Arduino/Processing sketches, Visual Basic (classic + .NET), Python.

Produces a per-function breakdown (name, kind, line, signature, doc, params,
returns, calls), an outline (includes, #define constants, types, globals,
classes, pragmas), a cleaned header-comment summary and keywords.

Parsing strategy (C family): comments, strings and preprocessor directives are
masked to spaces (same length, newlines kept) so offsets line up with the
original; braces/semicolons are then scanned scope by scope.  Doc comments and
signatures are taken from the original text.
"""
import os, re, bisect, ast, html

EXTS = {'c', 'h', '_c', '_h', 'cpp', 'cc', 'cxx', 'hpp', 'hh', 'hxx', 'i', 'ino', 'pde',
        'java', 'cs', 'js', 'py', 'vb', 'bas', 'frm', 'cls', 'ctl', 'idl', 'pjt_c'}
# note: '.m' deliberately not claimed - every .m in the archive is a Specctra PCB
# wiring file, not Objective-C/MATLAB.

MAX_FUNCS = 1500
MAX_I_FUNCS = 400
MAX_DOC = 1200
MAX_CALLS = 80
MAX_COMMENT_TEXT = 300_000

TYPE_NAMES = {
    'c': 'C source', 'h': 'C header', '_c': 'C source (backup copy)', '_h': 'C header (backup copy)',
    'pjt_c': 'C source (project copy)', 'cpp': 'C++ source', 'cc': 'C++ source', 'cxx': 'C++ source',
    'hpp': 'C++ header', 'hh': 'C++ header', 'hxx': 'C++ header',
    'i': 'Preprocessed C source (compiler intermediate)', 'ino': 'Arduino sketch (C++)',
    'pde': 'Arduino/Processing sketch', 'java': 'Java source', 'cs': 'C# source',
    'js': 'JavaScript source', 'idl': 'IDL interface definition', 'py': 'Python source',
    'vb': 'VB.NET source', 'bas': 'Visual Basic module', 'frm': 'Visual Basic form',
    'cls': 'Visual Basic class module', 'ctl': 'Visual Basic user control',
}
LANG_OF = {'c': 'c', 'h': 'c', '_c': 'c', '_h': 'c', 'pjt_c': 'c', 'i': 'c',
           'cpp': 'cpp', 'cc': 'cpp', 'cxx': 'cpp', 'hpp': 'cpp', 'hh': 'cpp', 'hxx': 'cpp',
           'ino': 'cpp', 'pde': 'cpp', 'java': 'java', 'cs': 'csharp', 'js': 'javascript',
           'idl': 'idl', 'py': 'python', 'vb': 'vbnet', 'bas': 'vb', 'frm': 'vb', 'cls': 'vb', 'ctl': 'vb'}
HEADER_EXTS = {'h', '_h', 'hpp', 'hh', 'hxx', 'idl'}

# ------------------------------------------------------------------ shared helpers
KEYWORDS = set("""if else for while do switch case default return sizeof typeof alignof goto break continue
asm __asm __asm__ _asm defined catch try throw throws new delete typeid static_cast dynamic_cast
reinterpret_cast const_cast decltype __attribute__ __declspec _Pragma __builtin_expect lock using
synchronized instanceof elif foreach in is not and or lambda print exec yield assert with await
function var let const void int char short long float double unsigned signed bool boolean byte
struct union enum class interface namespace operator super this base __typeof__ noexcept static
volatile register extern inline __inline auto""".split())

STORAGE = set("""static extern inline __inline __inline__ _inline register auto volatile public private
protected internal virtual override sealed abstract final native synchronized transient strictfp
friend explicit async partial unsafe readonly new __far __near far near _far _near __huge
__flash __eeprom __monitor __task __noreturn __ramfunc _Noreturn constexpr""".split())

ISR_MACROS = {'ISR', 'SIGNAL', 'INTERRUPT', 'EX_INTERRUPT_HANDLER', 'EX_EXCEPTION_HANDLER',
              'EX_REENTRANT_HANDLER', 'EX_NMI_HANDLER', 'EX_FIQ_HANDLER', 'IRQ_HANDLER',
              '__ISR', 'interrupt'}

CHIP_RE = re.compile(r'\b(AT(?:mega|MEGA|tiny|TINY|xmega|XMEGA)\d+\w*|AT90\w+|AT91\w+|ATSAM\w+|'
                     r'ADSP-?2\d{3,4}\w*|ADSP-?BF\d{3}\w*|BF5\d\d\w*|ADAU\d{4}\w*|AD\d{4}\w*|'
                     r'STM32\w+|STM8\w+|dsPIC\d+\w*|PIC1[0268][A-Z]*\d+\w*|PIC24\w+|PIC32\w+|'
                     r'MSP430\w*|LPC\d{3,4}\w*|MCF\d{4}\w*|TMS320\w+|XS1-\w+|CS\d{4}\w*|AK\d{4}\w*|'
                     r'SRC\d{4}\w*|DIR\d{4}\w*|PCM\d{4}\w*|WM\d{4}\w*|EP\d[A-Z]\d+\w*|'
                     r'SHARC|Blackfin|XMOS|FreeRTOS|ATmega|AVR|Cortex-M\d)\b')
PERIPH_RE = re.compile(r'\b(UART|USART|SPI|I2C|TWI|SPORT|DMA|ADC|DAC|PWM|EEPROM|LCD|OLED|CAN|USB|'
                       r'TIMER|Timer|GPIO|RTC|WDT|Watchdog|FPGA|CPLD|AES3|AES|SPDIF|S/PDIF|MADI|SDI|'
                       r'I2S|TDM|PLL|Ethernet|TCP|UDP|MIDI|RS232|RS485|Flash|SRAM|SDRAM|LED|'
                       r'Encoder|encoder|Keypad|keypad|codec|Codec|AVB)\b')

CP_RE = re.compile(r'copyright|\(c\)\s*\d|all rights reserved|licen[sc]e|warrant|redistribut|'
                   r'permission is hereby|this software is|provided "as is"|as is\b.*without|'
                   r'\$(?:Id|Log|Revision|Header|Date|Author|Source)\b|merchantab|fitness for a|'
                   r'disclaimer|neither the name|endorse or promote|source and binary forms|liable|damages|'
                   r'conditions (?:are|and) |following conditions|without specific prior|'
                   r'gnu general public|free software foundation|any later version', re.I)
DECOR_LINE = re.compile(r'^[\s\*=\-#/_~+.<>|:;!\\]*$')
LABEL_RE = re.compile(r'^\s*@?([A-Za-z][A-Za-z /\.]{1,28}?)\s*:\s*(.*)$')
STOP_LABEL = re.compile(r'revision|history|change\s*log|modification|changes|log\b', re.I)
DESC_LABEL = re.compile(r'desc|purpose|abstract|summary|brief|overview|function\b|module description', re.I)


def _norm(s):
    return re.sub(r'\s+', ' ', s).strip()


def clean_comment(txt):
    """Remove comment delimiters and decoration; returns cleaned multi-line text."""
    t = txt
    if t.startswith('/*'):
        t = t[2:]
        if t.endswith('*/'):
            t = t[:-2]
        t = t.lstrip('*!')
    if '&' in t:
        t = html.unescape(t)
    t = re.sub(r'\{@(?:link|code|linkplain)\s+([^}]*)\}', r'\1', t)
    t = re.sub(r'</?(?:p|br|code|b|i|em|strong|pre|ul|li|tt)\s*/?>', '', t, flags=re.I)
    out = []
    for ln in t.replace('\r', '').split('\n'):
        s = ln.strip()
        if s.startswith('//'):
            s = s.lstrip('/').lstrip('!<')
        elif s.startswith("'") or s.lower().startswith('rem '):
            s = s[1:] if s.startswith("'") else s[4:]
        elif s.startswith('#'):
            s = s.lstrip('#')
        s = re.sub(r'^\*+\s?', '', s.strip())
        s = re.sub(r'\s*\*+/?$', '', s)
        s = re.sub(r'^[=\-#*~_]{3,}\s*|\s*[=\-#*~_]{3,}$', '', s)
        s = s.strip()
        if DECOR_LINE.match(s):
            if out and out[-1] != '':
                out.append('')
            continue
        out.append(s)
    while out and out[-1] == '':
        out.pop()
    while out and out[0] == '':
        out.pop(0)
    return '\n'.join(out)


def looks_like_code(text):
    t = text.strip()
    if not t:
        return False
    lines = [l for l in t.split('\n') if l.strip()]
    codey = sum(1 for l in lines if re.search(r'[;{}]\s*$|^\s*(if|for|while|return|else)\b.*[(;{]|^\s*#\s*(include|define|if)|^\s*\w+\s*\(.*\)\s*;|^\s*[\w\[\]\.>-]+\s*[|&+\-*/]?=[^=]', l))
    return codey >= max(1, (len(lines) + 1) // 2)


def is_license(text):
    hits = len(CP_RE.findall(text))
    words = len(re.findall(r'[A-Za-z]{3,}', text))
    return hits >= 2 and (re.search(r'licen[sc]e|redistribut|warrant', text, re.I) is not None) and \
        (words < 400 or hits >= 4)


def strip_boiler(text):
    lines = [l for l in text.split('\n') if not CP_RE.search(l)]
    return '\n'.join(lines).strip()


def header_summary(text):
    """Turn a cleaned header comment into (summary, meta)."""
    meta = []
    lines = text.split('\n')
    desc, body, cur_label, in_desc, stop = [], [], None, False, False
    for ln in lines:
        if CP_RE.search(ln):
            continue
        tm = re.match(r'^\s*[@\\](author|version|since|date|file)\b\s*(.*)$', ln)
        if tm:
            if tm.group(2).strip() and tm.group(1) in ('author', 'version', 'date'):
                meta.append((tm.group(1).capitalize(), tm.group(2).strip()[:100]))
            continue
        m = LABEL_RE.match(ln)
        if m and len(m.group(1).split()) <= 4:
            lab, val = m.group(1).strip(), m.group(2).strip()
            cur_label = lab
            in_desc = bool(DESC_LABEL.search(lab))
            if STOP_LABEL.search(lab):
                stop = True
                continue
            stop = False
            ll = lab.lower()
            if val and len(val) < 120:
                if re.search(r'author|programmer|engineer|written by|created by', ll):
                    meta.append(('Author', val))
                elif re.search(r'^project|^product', ll):
                    meta.append(('Project', val))
                elif re.search(r'^date|^created', ll):
                    meta.append(('Date', val))
                elif re.search(r'^version|^rev', ll):
                    meta.append(('Version', val))
            if in_desc:
                if val:
                    desc.append(val)
                continue
            if re.search(r'file\s*name|^file$|^module$|^author|^date|^created|^version|^compiler|'
                         r'^target|^chip|^processor|^project|^platform|^tools?', ll):
                if val and not re.search(r'file\s*name|^file$|^author|^date|^created|^version', ll):
                    body.append(f'{lab}: {val}')
                continue
            if val:
                body.append(f'{lab}: {val}')
            continue
        if stop:
            continue
        if in_desc:
            desc.append(ln)
        else:
            body.append(ln)
    src = desc if any(d.strip() for d in desc) else body
    s = _norm(' '.join(x.strip() for x in src if x.strip()))
    s = re.sub(r'@(?:file|brief|author|date|version)\b\s*', '', s)
    if len(s) > 700:
        cut = s[:700]
        k = max(cut.rfind('. '), 400)
        s = cut[:k + 1].rstrip() + ' …' if k > 400 else cut.rstrip() + ' …'
    return s, meta


def parse_doc_params(doc):
    notes = {}
    ret = ''
    for m in re.finditer(r'[@\\]param(?:\s*\[\w+\])?\s+(\w+)\s*[-:]?\s*([^\n@\\]*)', doc):
        notes[m.group(1)] = m.group(2).strip()
    m = re.search(r'[@\\]returns?\s+([^\n@\\]*)', doc)
    if m:
        ret = m.group(1).strip()
    return notes, ret


def chips_keywords(text, func_names, extra=()):
    kws = list(extra)
    chips = {}
    for m in CHIP_RE.finditer(text[:3_000_000]):
        chips[m.group(1)] = chips.get(m.group(1), 0) + 1
    kws += [k for k, _ in sorted(chips.items(), key=lambda x: -x[1])[:5]]
    per = {}
    for m in PERIPH_RE.finditer(text[:3_000_000]):
        k = m.group(1)
        k = k.upper() if k.lower() not in ('encoder', 'keypad', 'codec', 'timer', 'flash', 'watchdog', 'ethernet') else k.capitalize()
        per[k] = per.get(k, 0) + 1
    kws += [k for k, _ in sorted(per.items(), key=lambda x: -x[1]) if _ >= 2][:5]
    kws += func_names[:6]
    seen, out = set(), []
    for k in kws:
        if k and k.lower() not in seen:
            seen.add(k.lower()); out.append(k)
    return out


def comment_paragraphs(comment_texts):
    pars, total = [], 0
    for t in comment_texts:
        if is_license(t) or looks_like_code(t):
            continue
        t = strip_boiler(t)
        if len(t) < 3 or not re.search(r'[A-Za-z]{3}', t):
            continue
        total += len(t)
        if total > MAX_COMMENT_TEXT:
            pars.append('… (further comments omitted)')
            break
        pars.append(t)
    return pars


# ------------------------------------------------------------------ C family
TOK = re.compile(r'//[^\n]*|/\*.*?(?:\*/|\Z)|"(?:\\.|[^"\\\n])*"?|\'(?:\\.|[^\'\\\n]){1,8}\'', re.S)
COMMENT_ONLY = re.compile(r'//[^\n]*|/\*.*?(?:\*/|\Z)', re.S)
PP_LINE = re.compile(r'^[ \t]*#', re.M)
NAME_TAIL = re.compile(r'(~?[A-Za-z_$][\w$]*(?:\s*(?:::|\.)\s*~?[A-Za-z_$][\w$]*)*|operator\s*(?:\(\)|[^\s\w(]+|\w+))\s*$')
TRAIL_OK = re.compile(r'^(?:\s|const\b|volatile\b|noexcept\b|override\b|final\b|throw\s*\([^)]*\)|'
                      r'throws\s+[\w.$<>,\s]+|where\s+[^{]*|__\w+\b|reentrant\b|interrupt\s*\d*|'
                      r'using\s+\d+|small\b|large\b|compact\b|\[\[.*?\]\]|=\s*0|=\s*default|=\s*delete|'
                      r'->\s*[\w:<>*&\s]+)*$', re.S)
CALL_RE = re.compile(r'(?<![\w$.>:])((?:[A-Za-z_$][\w$]*\s*(?:\.|->|::)\s*)*[A-Za-z_$][\w$]*)\s*\(')
CONTAINER_RE = re.compile(r'(?:^|\s)(struct|union|enum|class|interface|namespace|module|record)\b'
                          r'(?:\s+class\b)?\s*([A-Za-z_][\w:.]*)?\s*(.*)$', re.S)
DEAD_FN = re.compile(r'(?m)^[ \t]*(?:[A-Za-z_]\w*[ \t\*]+)+([A-Za-z_]\w*)[ \t]*\([^;{}()]*\)[ \t]*(?://[^\n]*)?\n?[ \t]*\{')
KR_RE = re.compile(r'^\s*((?:[A-Za-z_]\w*[\s\*]+)*?)([A-Za-z_]\w*)\s*\(\s*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*\)'
                   r'\s*([A-Za-z_][\w\s\*,\[\]]*)$')
JAVA_ANNOT = re.compile(r'@[A-Za-z_][\w.]*(?:\s*\((?:[^()]|\([^()]*\))*\))?')


class CParser:
    def __init__(self, text, ext, lang):
        self.text = text
        self.ext = ext
        self.lang = lang
        self.is_header = ext in HEADER_EXTS
        self.funcs, self.types, self.globals_, self.protos, self.classes = [], [], [], [], []
        self.notes = []
        self.proto_docs = {}
        self.mask()
        self.lines = [0] + [m.end() for m in re.finditer('\n', text)]

    # -------- masking
    def mask(self):
        t = self.text
        parts, comments, last = [], [], 0
        for m in TOK.finditer(t):
            s, e = m.span()
            parts.append(t[last:s])
            tok = m.group(0)
            if tok[0] == '/':
                comments.append((s, e, tok))
            parts.append(re.sub(r'[^\n]', ' ', tok))
            last = e
        parts.append(t[last:])
        masked = ''.join(parts)
        self.comments = comments
        self.cstarts = [c[0] for c in comments]
        # preprocessor directives
        directives, blanks = [], []
        pos = 0
        n = len(masked)
        for m in PP_LINE.finditer(masked):
            s = m.start()
            if s < pos:
                continue
            e = s
            while True:
                nl = masked.find('\n', e)
                if nl < 0:
                    e = n; break
                if masked[e:nl].rstrip().endswith('\\'):
                    e = nl + 1; continue
                e = nl; break
            pos = e
            raw = COMMENT_ONLY.sub(' ', t[s:e])
            raw = _norm(raw.replace('\\\n', ' '))
            directives.append((s, e, raw))
            blanks.append((s, e))
        self.directives = directives
        masked = self._blank(masked, blanks)
        # conditional compilation: drop #if 0 and alternate branches that unbalance braces
        stack, frames = [], []
        for s, e, raw in directives:
            m = re.match(r'#\s*(\w+)\s*(.*)', raw)
            if not m:
                continue
            d, arg = m.group(1), m.group(2)
            if d in ('if', 'ifdef', 'ifndef'):
                stack.append({'zero': d == 'if' and re.match(r'^\(?\s*0\s*\)?\s*$', arg) is not None,
                              'branches': [], 'cur': e})
            elif d in ('elif', 'else') and stack:
                f = stack[-1]
                f['branches'].append((f['cur'], s)); f['cur'] = e
            elif d == 'endif' and stack:
                f = stack.pop()
                f['branches'].append((f['cur'], s))
                frames.append(f)
        blanks = []
        for f in frames:
            br = f['branches']
            if f['zero']:
                blanks.append(br[0])
                continue
            if len(br) > 1:
                b0 = masked[br[0][0]:br[0][1]]
                if b0.count('{') != b0.count('}'):
                    blanks.extend(br[1:])
        if blanks:
            masked = self._blank(masked, blanks)
        self.masked = masked
        self.noise = sorted([(c[0], c[1]) for c in comments] + [(d[0], d[1]) for d in directives] + blanks)
        self.noise_starts = [x[0] for x in self.noise]

    @staticmethod
    def _blank(s, ranges):
        if not ranges:
            return s
        ranges = sorted(ranges)
        out, last = [], 0
        for a, b in ranges:
            if b <= last:
                continue
            a = max(a, last)
            out.append(s[last:a])
            out.append(re.sub(r'[^\n]', ' ', s[a:b]))
            last = b
        out.append(s[last:])
        return ''.join(out)

    def line_of(self, pos):
        return bisect.bisect_right(self.lines, pos)

    def clean_orig(self, a, b):
        """Original text in [a,b) with comments/directives removed, whitespace normalised."""
        out, last = [], a
        i = max(0, bisect.bisect_right(self.noise_starts, a) - 1)
        while i < len(self.noise) and self.noise[i][0] < b:
            s, e = self.noise[i]
            if e > last:
                if s > last:
                    out.append(self.text[last:s])
                out.append(' ')
                last = max(last, e)
            i += 1
        if last < b:
            out.append(self.text[last:b])
        return _norm(''.join(out))

    # -------- doc comments
    def doc_before(self, pos):
        m = self.masked
        i = bisect.bisect_left(self.cstarts, pos) - 1
        block = []
        limit = pos
        while i >= 0:
            s, e, tok = self.comments[i]
            if e > limit:
                i -= 1; continue
            if limit - e > 1500:
                break
            gap = re.sub(r'(?m)^[ \t]*#[ \t]*(?:pragma|line)\b.*$', '', self.text[e:limit])
            if gap.strip():
                break
            nls = self.text.count('\n', e, limit)
            if nls > (3 if not block else 2):
                break
            ls = self.text.rfind('\n', 0, s) + 1
            if self.text[ls:s].strip():   # trailing comment of a previous code line
                break
            if i == self.header_idx_end and self.header_used:
                break
            block.insert(0, tok)
            limit = s
            i -= 1
        if not block:
            return ''
        d = clean_comment('\n'.join(block)) if all(b.startswith('//') for b in block) else \
            '\n'.join(clean_comment(b) for b in block).strip()
        return '' if looks_like_code(d) else d

    def doc_trailing(self, a, b):
        """First comment starting in [a,b) on the same line as a."""
        i = bisect.bisect_left(self.cstarts, a)
        if i < len(self.comments):
            s, e, tok = self.comments[i]
            if s < b and '\n' not in self.text[a:s]:
                c = clean_comment(tok)
                return '' if looks_like_code(c) else c
        return ''

    def doc_in_body(self, a, b):
        i = bisect.bisect_left(self.cstarts, a + 1)
        while i < len(self.comments):
            s, e, tok = self.comments[i]
            if s >= b or self.text.count('\n', a, s) > 8:
                break
            ls = self.text.rfind('\n', 0, s) + 1
            if not self.masked[a + 1:s].strip() or (not self.text[ls:s].strip() and self.text.count('\n', a, s) <= 2):
                toks, j, last = [tok], i + 1, e
                while tok.startswith('//') and j < len(self.comments) and self.comments[j][0] < b:
                    s2, e2, t2 = self.comments[j]
                    if not t2.startswith('//') or self.text[last:s2].strip() or self.text.count('\n', last, s2) > 1:
                        break
                    toks.append(t2); last = e2; j += 1
                c = clean_comment('\n'.join(toks))
                if c and not looks_like_code(c):
                    return c
            i += 1
        return ''

    # -------- scanning
    def run(self):
        m = self.masked
        toks = [(x.start(), x.group(0)) for x in re.finditer(r'[{};]', m)]
        self.tpos = [p for p, _ in toks]
        self.tch = [c for _, c in toks]
        match = [-1] * len(toks)
        st = []
        for k, c in enumerate(self.tch):
            if c == '{':
                st.append(k)
            elif c == '}':
                if st:
                    match[st.pop()] = k
        if st:
            self.notes.append(f'{len(st)} unbalanced "{{" (possibly conditional code); parse may be approximate.')
        self.match = match
        self.header_comment()
        self.scope(0, len(toks), 0, len(m), [], top=True)

    def header_comment(self):
        self.header_used = False
        self.header_idx_end = -2
        self.header_text = ''
        if not self.comments:
            return
        m = self.masked
        # first code token
        fc = re.search(r'\S', m)
        first_code = fc.start() if fc else len(m)
        block, i, last_e = [], 0, None
        while i < len(self.comments):
            s, e, tok = self.comments[i]
            if s > first_code and self.lang not in ('java', 'csharp', 'javascript'):
                break
            if self.lang in ('java', 'csharp', 'javascript') and s > first_code:
                # allow comment after package/import lines, before the first '{'
                br = m.find('{')
                if br >= 0 and s > br:
                    break
                if re.search(r'[^\s;]', re.sub(r'(?m)^\s*(package|import|using)\b[^;]*;', '', m[first_code:s])):
                    break
            if last_e is not None and m[last_e:s].strip():
                if block:
                    break
            if last_e is not None and self.text.count('\n', last_e, s) > 2 and block:
                break
            block.append(tok); last_e = e; self.header_idx_end = i
            i += 1
        if not block:
            return
        txt = '\n'.join(clean_comment(b) for b in block)
        # a short comment sitting directly on the first function is that function's doc
        q = re.compile(r'\S').search(m, last_e)
        if q and self.text.count('\n', last_e, q.start()) <= 2 and len([l for l in txt.split('\n') if l.strip()]) < 4:
            nxt = re.match(r'[^;{}]*', m[q.start():q.start() + 2000]).group(0)
            end = q.start() + len(nxt)
            if '(' in nxt and end < len(m) and m[end] == '{' and not self._has_assign(nxt):
                self.header_idx_end = -2
                return
        if is_license(txt):
            self.header_used = True      # don't reuse the licence as a function doc
            keep = []
            pm = re.search(r'(?im)^\s*(?:project|module|product)\s*:.*$', txt)
            if pm:
                keep.append(pm.group(0).strip())
            dm = re.search(r'(?ims)^\s*(?:@brief|description|purpose|abstract|brief|overview)\b\s*:?.*', txt)
            if dm:
                dl = []
                for ln in dm.group(0).strip().split('\n'):
                    if CP_RE.search(ln) or (not ln.strip() and dl):
                        break
                    dl.append(ln)
                keep.append('\n'.join(dl).strip())
            self.header_text = '\n'.join(keep) if dm else ''
            if not dm:
                br = m.find('{')
                for j in range(0, min(len(self.comments), self.header_idx_end + 2)):
                    if br >= 0 and self.comments[j][0] > br:
                        break
                    nxt = clean_comment(self.comments[j][2])
                    if len(nxt) >= 60 and not is_license(nxt) and not looks_like_code(nxt):
                        self.header_text = nxt
                        self.header_idx_end = max(self.header_idx_end, j)
                        break
            return
        if len(re.sub(r'\s', '', txt)) < 15:
            return
        self.header_text = txt
        self.header_used = True

    def scope(self, ti, tj, a, b, names, top=False, kind_ctx='file'):
        """Scan tokens ti..tj (positions within [a,b)) at one nesting level."""
        m = self.masked
        stmt = a
        kr = None            # (start, [stmts]) candidate K&R header
        k = ti
        cls_name = names[-1] if names else ''
        while k < tj:
            if len(self.funcs) > MAX_FUNCS:
                return
            p, c = self.tpos[k], self.tch[k]
            if c == ';':
                self.statement(stmt, p, names, kind_ctx)
                seg = m[stmt:p]
                if kr is not None:
                    if re.match(r'^\s*[\w\s\*,\[\]()]+$', seg) and re.search(r'\w', seg):
                        kr[1].append((stmt, p))
                    else:
                        kr = None
                if kr is None and self.lang == 'c' and kind_ctx == 'file':
                    mm = KR_RE.match(seg)
                    if mm and not set(re.findall(r'\w+', mm.group(3))) & {'void', 'int', 'char', 'long', 'short', 'unsigned', 'float', 'double', 'const', 'struct'}:
                        kr = (stmt + (len(seg) - len(seg.lstrip())), [], mm, len(self.globals_) - 1)
                stmt = p + 1
                k += 1
                continue
            if c == '}':
                stmt = p + 1
                k += 1
                continue
            # '{'
            close_k = self.match[k]
            close = self.tpos[close_k] if close_k >= 0 else b
            hdr = m[stmt:p]
            res = None
            if kr is not None and not hdr.strip():
                res = self.function(kr[0], kr[0], p, close, names, kind_ctx, kr_decls=kr)
                if res:
                    del self.globals_[max(0, kr[3]):]
                kr = None
                if res:
                    k = (close_k + 1) if close_k >= 0 else tj
                    stmt = (close + 1)
                    continue
            kr = None
            res = self.block(stmt, p, close, close_k, names, kind_ctx, k)
            if close_k < 0:
                return
            if res == 'continue_stmt':      # struct/initializer: statement goes on until ';'
                k = close_k + 1
                continue
            k = close_k + 1
            stmt = close + 1

    def block(self, stmt, p, close, close_k, names, kind_ctx, k):
        m = self.masked
        raw = m[stmt:p]
        ws = re.search(r'\S', raw)
        if not ws:
            return 'skip'
        start = stmt + ws.start()
        hdr = raw[ws.start():]
        # strip C++ access labels at start
        mm = re.match(r'^(?:(?:public|private|protected|internal|signals|slots|Q_SLOTS)\s*:(?!:)\s*)+', hdr)
        if mm:
            start += mm.end(); hdr = hdr[mm.end():]
        h = hdr
        if self.lang in ('java', 'csharp', 'javascript', 'idl'):
            h = JAVA_ANNOT.sub(lambda x: ' ' * len(x.group(0)), h)
        if self.lang == 'csharp' or self.lang == 'idl':
            h = re.sub(r'^\s*(\[[^\]]*\]\s*)+', lambda x: ' ' * len(x.group(0)), h)
        hs = h.strip()
        if not hs:
            return 'skip'
        first = hs.split()[0].split('(')[0]
        if first in ('if', 'else', 'for', 'while', 'do', 'switch', 'try', 'catch', 'finally', 'case',
                     'default', 'return', 'synchronized', 'unsafe', 'checked', 'fixed', 'lock', 'using') and \
                not re.match(r'using\s+namespace', hs):
            if self.lang == 'javascript':
                self.scope(k + 1, close_k if close_k >= 0 else len(self.tpos), p + 1, close, names, kind_ctx=kind_ctx)
            return 'skip'
        if re.match(r'^static\s*$', hs):     # Java static initialiser
            return 'skip'
        # extern "C" {
        if re.match(r'^extern\s*$', hs):
            self.scope(k + 1, close_k if close_k >= 0 else len(self.tpos), p + 1, close, names, kind_ctx=kind_ctx)
            return 'skip'
        # JS function forms
        if self.lang == 'javascript':
            jm = (re.match(r'^(?:export\s+)?(?:async\s+)?function\s*\*?\s*([\w$]+)\s*\(', hs) or
                  re.match(r'^(?:(?:var|let|const)\s+)?([\w$.]+)\s*[=:]\s*(?:async\s+)?function\b\s*[\w$]*\s*\(', hs) or
                  re.match(r'^(?:(?:var|let|const)\s+)?([\w$.]+)\s*[=:]\s*(?:async\s+)?\(?[\w$,\s]*\)?\s*=>\s*$', hs) or
                  (re.match(r'^(?:static\s+|async\s+|get\s+|set\s+)*([\w$]+)\s*\([^)]*\)\s*$', hs) if kind_ctx == 'class' else None))
            if jm:
                self.function(start, start, p, close, names, kind_ctx, js_name=jm.group(1))
                return 'skip'
            cm = re.match(r'^(?:export\s+)?(?:default\s+)?class\s+([\w$]+)', hs)
            if cm:
                self.add_class('class', cm.group(1), start, hs, k, close_k, p, close, names)
                return 'skip'
            self.scope(k + 1, close_k if close_k >= 0 else len(self.tpos), p + 1, close, names, kind_ctx=kind_ctx)
            return 'skip'
        # initialiser: '=' at paren depth 0 (not ==, <=, ...)
        if self._has_assign(h):
            return 'continue_stmt'
        # template prefix
        hh = re.sub(r'^\s*template\s*<[^{;]*?>\s*(?=[A-Za-z_])', lambda x: ' ' * len(x.group(0)), h)
        # function?
        fres = self.function(start, start, p, close, names, kind_ctx, hdr_override=hh)
        if fres:
            return 'skip'
        # struct / class / namespace / enum
        cm = CONTAINER_RE.search(hh)
        if cm and '(' not in hh[:cm.start()]:
            kw, nm, rest = cm.group(1), (cm.group(2) or ''), cm.group(3)
            if kw == 'namespace' or kw == 'module':
                self.scope(k + 1, close_k if close_k >= 0 else len(self.tpos), p + 1, close,
                           names + ([nm] if nm and self.lang not in ('c', 'cpp') else []), kind_ctx='ns')
                return 'skip'
            if kw in ('class', 'interface', 'record') or (kw == 'struct' and self.lang in ('cpp', 'csharp', 'idl') and
                                                          re.search(r'\(', m[p:close] or '')) or \
                    (kw == 'enum' and self.lang == 'java'):
                self.add_class(kw, nm, start, hs, k, close_k, p, close, names)
                return 'continue_stmt' if self.lang in ('c', 'cpp', 'idl') else 'skip'
            # plain C aggregate
            body = m[p + 1:close]
            if kw == 'enum':
                members = [x.split('=')[0].strip() for x in body.split(',') if x.strip()]
                members = [x for x in members if re.match(r'^\w+$', x)]
                info = f"{len(members)} values: " + ', '.join(members[:12]) + (' …' if len(members) > 12 else '')
            else:
                fields = [f for f in body.split(';') if f.strip()]
                info = f'{len(fields)} member{"s" if len(fields) != 1 else ""}'
            after = m[close + 1:close + 400]
            tn = re.match(r'^\s*([^;{]*);', after)
            tdname = _norm(tn.group(1)) if tn else ''
            is_td = bool(re.search(r'\btypedef\b', hh))
            q = ('::'.join(names) + '::') if names else ''
            label = f"{'typedef ' if is_td else ''}{kw} `{q}{nm or '(anonymous)'}`"
            if tdname:
                label += f" → `{tdname}`" if is_td else f" (declares `{tdname}`)"
            self.types.append(f"{label} — {info} (line {self.line_of(start)})")
            self._td_handled = close
            return 'continue_stmt'
        # C# property / unknown block inside class
        if kind_ctx == 'class' and re.match(r'^[\w<>\[\],.\s?*]+\s+([A-Za-z_]\w*)\s*$', hs) and self.lang == 'csharp':
            pm = re.match(r'^(.*?)([A-Za-z_]\w*)\s*$', hs)
            self.funcs.append({'name': '.'.join(names + [pm.group(2)]), 'kind': 'property',
                               'line': self.line_of(start), 'signature': self.clean_orig(start, p),
                               'doc': self.doc_before(start), 'returns': _norm(self._ret(pm.group(1))),
                               'params': [], 'calls': []})
            return 'skip'
        return 'continue_stmt' if re.search(r'\w', hs) and not hs.endswith(')') else 'skip'

    @staticmethod
    def _has_assign(h):
        d = 0
        for i, ch in enumerate(h):
            if ch in '([<' and ch != '<':
                d += 1
            elif ch in ')]':
                d -= 1
            elif ch == '=' and d <= 0:
                prev = h[i - 1] if i else ''
                nxt = h[i + 1] if i + 1 < len(h) else ''
                if prev not in '=!<>+-*/%&|^' and nxt != '=':
                    return True
        return False

    def add_class(self, kw, nm, start, hs, k, close_k, p, close, names):
        q = names + [nm or '(anonymous)']
        ext = ''
        em = re.search(r'\bextends\s+([\w.<>, ]+?)(?=\s+implements\b|$)', hs)
        if em:
            ext += f' extends `{_norm(em.group(1))}`'
        im = re.search(r'\bimplements\s+([\w.<>, ]+)', hs)
        if im:
            ext += f' implements `{_norm(im.group(1))}`'
        bm = re.search(r'(?<!:):(?!:)\s*([^{]+)$', hs) if self.lang in ('cpp', 'csharp', 'idl') else None
        if bm:
            ext += f' : `{_norm(bm.group(1))}`'
        before = len(self.funcs)
        fields_before = len(self.globals_)
        self.class_fields = []
        saved = getattr(self, '_fields', None)
        self._fields = []
        self.scope(k + 1, close_k if close_k >= 0 else len(self.tpos), p + 1, close, q, kind_ctx='class')
        nmeth = len(self.funcs) - before
        fields = self._fields
        self._fields = saved
        line = self.line_of(start)
        sep = '.' if self.lang != 'cpp' else '::'
        s = f"{kw} `{sep.join(q)}`{ext} (line {line}) — {nmeth} method{'s' if nmeth != 1 else ''}"
        if fields:
            s += f"; fields: " + ', '.join(f'`{f}`' for f in fields[:20]) + (' …' if len(fields) > 20 else '')
        self.classes.append(s)
        if self.lang in ('c', 'cpp', 'idl'):
            self._td_handled = close
        doc = self.doc_before(start)
        self.class_docs = getattr(self, 'class_docs', [])
        if doc:
            self.class_docs.append(doc)

    def _ret(self, prefix):
        words = []
        p = prefix
        if ')' in p:                       # macro cruft before the real return type
            p = p[p.rfind(')') + 1:]
        p = re.sub(r'\binterrupt\s*\[[^\]]*\]', ' ', p)
        p = re.sub(r'\[[^\]]*\]', ' ', p) if self.lang == 'c' else p
        for w in re.findall(r'[\w$<>\[\],.?:]+|\*+|&+', p):
            if w in STORAGE or w in ('__interrupt', 'interrupt', '__irq', '__fiq', 'typedef', 'template') \
                    or re.match(r'^__\w+__$', w):
                continue
            words.append(w)
        r = ' '.join(words)
        r = re.sub(r'\s+\*', '*', r)
        return r

    def function(self, start, name_from, p, close, names, kind_ctx, kr_decls=None, hdr_override=None, js_name=None):
        """Try to record a function whose header is masked[start:p] and body (p, close)."""
        m = self.masked
        if js_name:
            gm = re.search(r'\(', m[start:p])
            params_raw, pa = '', p
            if gm:
                o = start + gm.start()
                cl = self._match_paren(m, o, p)
                params_raw = m[o + 1:cl] if cl else ''
                pa = o + 1
            self._record(js_name, 'function' if kind_ctx != 'class' else 'method', start, p, close,
                         names, params_raw, pa, '', kind_ctx)
            return True
        if kr_decls:
            mm = kr_decls[2]
            name = mm.group(2)
            prefix = mm.group(1)
            decls = [mm.group(4)] + [m[x:y] for x, y in kr_decls[1]]
            types = {}
            for d in decls:
                parts = self._split_top(_norm(d))
                if not parts:
                    continue
                btype = ''
                m1 = re.match(r'^(.*?)([\*\s]*)([A-Za-z_]\w*)\s*((?:\[[^\]]*\])*)\s*$', parts[0])
                if m1:
                    btype = m1.group(1).strip()
                    types[m1.group(3)] = (btype + ' ' + m1.group(2).strip() + m1.group(4)).strip()
                for pp in parts[1:]:
                    m2 = re.match(r'^([\*\s]*)([A-Za-z_]\w*)\s*((?:\[[^\]]*\])*)\s*$', pp)
                    if m2 and btype:
                        types[m2.group(2)] = (btype + ' ' + m2.group(1).strip() + m2.group(3)).strip()
            params = [(n_, types.get(n_, 'int (implicit)'), '') for n_ in
                      [x.strip() for x in mm.group(3).split(',') if x.strip()]]
            self._record(name, None, start, p, close, names, None, None, prefix, kind_ctx, params_override=params)
            return True
        hdr = hdr_override if hdr_override is not None else m[start:p]
        hdr = self._blank_attrs(hdr)
        # C++ ctor initialiser list: cut at ') :'
        cut = re.search(r'\)\s*:(?!:)', hdr)
        if cut and self.lang in ('cpp', 'csharp'):
            hdr = hdr[:cut.start() + 1] + ' ' * (len(hdr) - cut.start() - 1)
        groups = self._top_groups(hdr)
        for o, cl in groups:
            before = hdr[:o]
            nm = NAME_TAIL.search(before)
            if not nm:
                continue
            name = re.sub(r'\s+', '', nm.group(1)) if not nm.group(1).startswith('operator') else _norm(nm.group(1))
            base = re.split(r'::|\.', name)[-1]
            if base in KEYWORDS and base not in ISR_MACROS and base != 'interrupt':
                continue
            trail = hdr[cl + 1:]
            if not TRAIL_OK.match(trail):
                continue
            prefix = before[:nm.start()]
            if self._has_assign(prefix):
                return False
            if re.search(r'\b(struct|union|enum|class)\s*$', prefix):
                return False
            # macro-generated: ISR(vect) / PROCESS_THREAD(x,...) with no return type
            params_raw = hdr[o + 1:cl]
            kind = None
            if not prefix.strip() and (base in ISR_MACROS or (base.isupper() and len(base) > 2 and self.lang == 'c')):
                arg0 = _norm(params_raw).split(',')[0].strip()
                if base in ISR_MACROS:
                    kind = 'isr'
                    params_raw = None
                    name = f'{base}({arg0})' if arg0 else base
                    if base.startswith('EX_') and arg0:
                        name = arg0
                else:
                    kind = 'macro-defined function'
                    name = f'{base}({arg0})' if arg0 else base
            self._record(name, kind, start, p, close, names, params_raw, start + o + 1, prefix, kind_ctx)
            return True
        return False

    def _prev_semicolon(self, pos):
        return self.masked.rfind(';', 0, pos)

    @staticmethod
    def _match_paren(s, o, limit):
        d = 0
        for i in range(o, min(limit, len(s))):
            ch = s[i]
            if ch == '(':
                d += 1
            elif ch == ')':
                d -= 1
                if d == 0:
                    return i
        return None

    @staticmethod
    def _top_groups(h):
        out, d, o = [], 0, -1
        for i, ch in enumerate(h):
            if ch == '(':
                if d == 0:
                    o = i
                d += 1
            elif ch == ')':
                d -= 1
                if d == 0 and o >= 0:
                    out.append((o, i))
                if d < 0:
                    d = 0
        return out

    def _blank_attrs(self, h):
        for kw in ('__attribute__', '__declspec', '_Pragma', '__asm__', 'asm', '__asm', 'AT', '__at', '_at_'):
            idx = 0
            while True:
                j = h.find(kw, idx)
                if j < 0:
                    break
                if (j and (h[j - 1].isalnum() or h[j - 1] == '_')) or not re.match(r'\s*\(', h[j + len(kw):]):
                    idx = j + len(kw); continue
                o = h.find('(', j)
                cl = self._match_paren(h, o, len(h))
                if cl is None:
                    break
                h = h[:j] + ' ' * (cl + 1 - j) + h[cl + 1:]
                idx = cl + 1
        return h

    @staticmethod
    def _split_top(s):
        parts, d, cur = [], 0, []
        for ch in s:
            if ch in '(<[{':
                d += 1
            elif ch in ')>]}':
                d -= 1
            if ch == ',' and d <= 0:
                parts.append(''.join(cur)); cur = []
            else:
                cur.append(ch)
        if ''.join(cur).strip():
            parts.append(''.join(cur))
        return [x.strip() for x in parts]

    def _params(self, raw, abs_start):
        """Parse a parameter list (masked text) -> [(name, type, note)]."""
        if raw is None:
            return []
        if not raw.strip() or raw.strip() == 'void':
            return []
        out = []
        d, seg_start = 0, 0
        segs = []
        for i, ch in enumerate(raw + ','):
            if ch in '(<[':
                d += 1
            elif ch in ')>]':
                d -= 1
            elif ch == ',' and d <= 0:
                segs.append((seg_start, i)); seg_start = i + 1
        notes = {}
        if abs_start is not None and segs:
            end_abs = abs_start + len(raw)
            eol = self.text.find('\n', end_abs)
            eol = len(self.text) if eol < 0 else eol
            ci = bisect.bisect_left(self.cstarts, abs_start)
            while ci < len(self.comments) and self.comments[ci][0] < eol:
                off = self.comments[ci][0] - abs_start
                si = len(segs) - 1
                for j, (sa, sb) in enumerate(segs):
                    if off < sb:
                        si = j; break
                if off >= len(raw):
                    si = len(segs) - 1
                elif si > 0 and '\n' not in self.text[abs_start + segs[si][0]:abs_start + off]:
                    si -= 1
                txt = _norm(clean_comment(self.comments[ci][2]))[:200]
                if txt and si not in notes:
                    notes[si] = txt
                ci += 1
        for idx, (a, b) in enumerate(segs):
            s = _norm(raw[a:b])
            if not s:
                continue
            note = notes.get(idx, '')
            dflt = ''
            if '=' in s and self.lang != 'c':
                s, dflt = s.split('=', 1)
                s = s.strip(); dflt = dflt.strip()
            if s in ('...',):
                out.append(('...', 'variadic', note)); continue
            fp = re.match(r'^(.*?)\(\s*[\*&^]\s*([A-Za-z_]\w*)\s*\)\s*(\(.*\))\s*$', s)
            if fp:
                out.append((fp.group(2), f'{fp.group(1).strip()} (*)' + fp.group(3), note)); continue
            mm = re.match(r'^(.*?)([A-Za-z_$][\w$]*)\s*((?:\[[^\]]*\]\s*)*)$', s)
            if mm and mm.group(1).strip() and mm.group(1).strip() not in ('struct', 'union', 'enum', 'unsigned', 'signed', 'const'):
                typ = (mm.group(1).strip() + (' ' + mm.group(3).replace(' ', '') if mm.group(3) else '')).strip()
                typ = re.sub(r'\s+\*', '*', typ)
                if self.lang == 'javascript':
                    out.append((mm.group(2), '', note)); continue
                out.append((mm.group(2), typ + (f' = {dflt}' if dflt else ''), note))
            elif mm and self.lang in ('javascript', 'python'):
                out.append((mm.group(2), f'= {dflt}' if dflt else '', note))
            else:
                out.append(('(unnamed)', s, note))
        return out

    def _calls(self, a, b, own):
        seen, out = set(), []
        for mm in CALL_RE.finditer(self.masked, a, b):
            nm = re.sub(r'\s+', '', mm.group(1))
            nm = re.sub(r'^this(?:\.|->)', '', nm)
            base = re.split(r'\.|->|::', nm)[-1]
            first = re.split(r'\.|->|::', nm)[0]
            if base in KEYWORDS or first in ('new',):
                continue
            pre = self.masked[max(a, mm.start() - 5):mm.start()]
            if re.search(r'\bnew\s+$', pre):
                continue
            if nm not in seen:
                seen.add(nm); out.append(nm)
                if len(out) >= MAX_CALLS:
                    break
        return out

    def _record(self, name, kind, start, p, close, names, params_raw, pabs, prefix, kind_ctx,
                params_override=None, is_proto=False):
        sep = '::' if self.lang == 'cpp' else '.'
        base = re.split(r'::|\.', name)[-1]
        full = sep.join(names + [name]) if names and kind_ctx == 'class' else name
        if names and kind_ctx == 'ns' and self.lang in ('csharp', 'idl', 'java'):
            full = '.'.join(names + [name])
        pre_words = set(re.findall(r'[\w$]+', prefix or ''))
        if kind is None:
            if is_proto:
                kind = 'prototype' if kind_ctx != 'class' else ('abstract method' if self.lang in ('java', 'csharp') else 'method declaration')
            elif kind_ctx == 'class' or '::' in name or (self.lang in ('java', 'csharp') and kind_ctx != 'file'):
                cls = names[-1] if names else name.split('::')[0]
                kind = 'constructor' if base == cls or base == (re.split(r'::|\.', name)[-2] if len(re.split(r'::|\.', name)) > 1 else None) else 'method'
                if base.startswith('~'):
                    kind = 'destructor'
            else:
                kind = 'function'
            if not is_proto and (pre_words & {'__interrupt', 'interrupt', '__irq', '__fiq', '_ISR', '__ISR'} or
                                 base in self.isr_names or re.search(r'(IRQHandler|_Handler|_ISR|_isr|Isr)$', base) or
                                 self.pragma_isr(start)):
                kind = 'isr'
            elif kind == 'function' and 'static' in pre_words:
                kind = 'static function'
            elif kind == 'function' and pre_words & {'inline', '__inline', '__inline__', '_inline'}:
                kind = 'inline function'
        if is_proto:
            sig = self.clean_orig(start, p) + ';'
        else:
            sig = self.clean_orig(start, p)
        if len(sig) > 600:
            sig = sig[:600] + ' …'
        doc = self.doc_before(start)
        if not doc and not is_proto:
            doc = self.proto_docs.get(name, '')
        if not doc:
            doc = self.doc_trailing(p if not is_proto else p, (close if not is_proto else p + 300))
        if not doc and not is_proto:
            doc = self.doc_in_body(p, close)
        if is_proto and not doc:
            doc = self.doc_trailing(p, p + 300)
        doc = strip_boiler(re.sub(r'[@\\]brief\s*', '', doc))
        if len(doc) > MAX_DOC:
            doc = doc[:MAX_DOC].rstrip() + ' …'
        params = params_override if params_override is not None else self._params(params_raw, pabs)
        if kind == 'isr' and params_raw is None and params_override is None and '(' in name:
            params = [('vector', name[name.index('(') + 1:-1], 'interrupt vector / source')]
        dnotes, dret = parse_doc_params(doc)
        if dnotes:
            params = [(a, b, c or dnotes.get(a, '')) for a, b, c in params]
        ret = self._ret(prefix) if kind not in ('constructor', 'destructor', 'isr', 'macro-defined function') \
            or (kind == 'isr' and prefix.strip()) else ''
        if not ret and self.lang == 'c' and kind in ('function', 'static function') and prefix is not None and not prefix.strip():
            ret = 'int (implicit)'
        if dret:
            ret = (ret + ' — ' if ret else '') + dret
        f = {'name': full, 'kind': kind, 'line': self.line_of(start), 'signature': sig, 'doc': doc,
             'params': params, 'returns': ret, 'calls': [] if is_proto else self._calls(p + 1, close, name)}
        f['_pos'] = start
        self.funcs.append(f)

    def pragma_isr(self, start):
        """#pragma vector=... / #pragma interrupt directly before the function."""
        i = bisect.bisect_left(self.dstarts, start) - 1
        while i >= 0:
            s, e, raw = self.directives[i]
            if self.masked[e:start].strip():
                return False
            if re.match(r'#\s*pragma\s+(vector|interrupt|isr|INTERRUPT|interrupt_level|TRAPS_ENTRY|code\s+\w*isr)', raw, re.I):
                return True
            if not re.match(r'#\s*pragma', raw):
                return False
            i -= 1
        return False

    def statement(self, a, b, names, kind_ctx):
        """Analyse a ';'-terminated statement: prototype, global, typedef, field."""
        m = self.masked
        seg = m[a:b]
        ws = re.search(r'\S', seg)
        if not ws:
            return
        start = a + ws.start()
        if getattr(self, '_td_handled', -1) >= a:
            return
        s = _norm(seg)
        s = re.sub(r'^(?:(?:public|private|protected|internal|signals|slots)\s*:(?!:)\s*)+', '', s)
        if self.lang in ('java', 'csharp', 'idl'):
            s2 = JAVA_ANNOT.sub(' ', s).strip()
        else:
            s2 = s
        if not s2:
            return
        if re.match(r'^(package|import|using|#|return|break|goto|continue)\b', s2):
            if re.match(r'^(import|using)\b', s2) and kind_ctx != 'class':
                self.imports.append(s2)
            return
        if re.match(r'^typedef\b', s2):
            fp = re.search(r'\(\s*\*\s*(\w+)\s*\)', s2)
            nm = fp.group(1) if fp else (re.findall(r'(\w+)\s*(?:\[[^\]]*\])*\s*$', s2) or ['?'])[0]
            val = s2[7:].strip()
            if not fp:
                val = re.sub(r'\b' + re.escape(nm) + r'\s*((?:\[[^\]]*\])*)\s*$', r'\1', val).strip()
            self.types.append(f"typedef `{nm}` = `{val.replace('`', '')[:120]}` (line {self.line_of(start)})")
            return
        h = self._blank_attrs(s2)
        groups = self._top_groups(h)
        if groups and not self._has_assign(h[:groups[0][0]]):
            for o, cl in groups:
                before = h[:o]
                nm = NAME_TAIL.search(before)
                if not nm:
                    continue
                name = re.sub(r'\s+', '', nm.group(1))
                base = re.split(r'::|\.', name)[-1]
                if base in KEYWORDS:
                    break
                if not TRAIL_OK.match(h[cl + 1:]):
                    continue
                prefix = before[:nm.start()]
                if not prefix.strip() and kind_ctx != 'class':
                    break     # macro invocation like FOO(x);
                # record prototype
                if self.is_header or kind_ctx == 'class' or self.lang in ('idl',):
                    # map params back to original positions approximately (masked seg start)
                    self._proto_from_masked(name, start, b, prefix, kind_ctx, names)
                else:
                    self.protos.append((name, self.line_of(start)))
                    nl = self.text.find('\n', b)
                    nxt = self.text[nl + 1:self.text.find('\n', nl + 1) if nl >= 0 else nl].strip() if nl >= 0 else ''
                    solo = not nxt or nxt.startswith(('/', '#'))
                    if name not in self.proto_docs:
                        d = (self.doc_before(start) if solo else '') or self.doc_trailing(b, b + 300)
                        if d:
                            self.proto_docs[name] = d
                return
        # variable / field
        if kind_ctx == 'class':
            mm = re.match(r'^(.*?)([A-Za-z_$][\w$]*)\s*(?:\[[^\]]*\]\s*)*(?:=.*)?$', s2)
            if mm and getattr(self, '_fields', None) is not None:
                self._fields.append(mm.group(2))
            return
        if kind_ctx in ('file', 'ns'):
            parts = self._split_top(s2)
            decl = ', '.join(x.split('=')[0].strip() for x in parts) if parts else s2
            if len(decl) > 160:
                decl = decl[:160] + ' …'
            if not re.search(r'\w', decl) or not re.search(r'\s|\*', decl):
                return
            self.globals_.append(f"`{decl.replace('`', '')}` (line {self.line_of(start)})")

    def _proto_from_masked(self, name, start, end, prefix, kind_ctx, names):
        m = self.masked
        seg = m[start:end]
        h = self._blank_attrs(seg)
        groups = self._top_groups(h)
        o = cl = None
        for go, gc in groups:
            nm = NAME_TAIL.search(h[:go])
            if nm and re.sub(r'\s+', '', nm.group(1)) == name:
                o, cl = go, gc
                break
        params_raw = h[o + 1:cl] if o is not None else ''
        pref = h[:o] if o is not None else ''
        nm = NAME_TAIL.search(pref)
        pref = pref[:nm.start()] if nm else pref
        self._record(name, None, start, end, end, names, params_raw, start + o + 1 if o is not None else None,
                     pref, kind_ctx, is_proto=True)


def c_outline(P, main_file_ranges=None):
    out = []
    incs, defs, macros, pragmas = [], [], [], []
    for s, e, raw in P.directives:
        if main_file_ranges is not None and not main_file_ranges(s):
            continue
        mm = re.match(r'#\s*(\w+)\s*(.*)', raw)
        if not mm:
            continue
        d, arg = mm.group(1), mm.group(2)
        if d in ('include', 'import'):
            incs.append(arg.strip())
        elif d == 'define':
            fm = re.match(r'([A-Za-z_]\w*)\(([^)]*)\)\s*(.*)', arg)
            if fm:
                macros.append((fm, s, raw))
            else:
                dm = re.match(r'([A-Za-z_]\w*)\s*(.*)', arg)
                if dm:
                    defs.append((dm.group(1), dm.group(2), P.line_of(s), s))
        elif d == 'pragma':
            pragmas.append(f"`{raw.replace('`', '')[:140]}` (line {P.line_of(s)})")
    return incs, defs, macros, pragmas


def extract_c(path, text, ext):
    lang = LANG_OF.get(ext, 'c')
    if ext in ('h', '_h') and re.search(r'^\s*(class\s+\w+[^;]*\{|namespace\s+\w+|template\s*<)', text[:400000], re.M):
        lang = 'cpp'
    P = CParser(text, ext, lang)
    nonempty = [l for l in text[:500000].split('\n') if l.strip()]
    asm_like = len(nonempty) > 5 and sum(1 for l in nonempty if re.match(r'^\s*;', l) or
                                         re.match(r'^\s*\.(equ|set|org|include|def)\b', l, re.I)) > 0.2 * len(nonempty)
    P.imports = []
    P.dstarts = [d[0] for d in P.directives]
    P.isr_names = set()
    for s, e, raw in P.directives:
        mm = re.match(r'#\s*pragma\s+(?:interrupt_handler|interrupt|isr|INTERRUPT|interrupt_level\s+\d+)\s+([\w:\s]+)', raw)
        if mm:
            for tok in mm.group(1).split():
                P.isr_names.add(tok.split(':')[0])
    # .i: map positions to source files via line markers
    in_main = None
    marker_info = None
    if ext == 'i':
        markers = []
        for s, e, raw in P.directives:
            mm = re.match(r'#\s*(?:line\s+)?(\d+)\s+"([^"]*)"', P.text[s:e].strip())
            if mm:
                markers.append((e + 1, int(mm.group(1)), mm.group(2)))
        if markers:
            stem = os.path.splitext(os.path.basename(path))[0].lower()
            files = [mk[2] for mk in markers]
            main = next((f for f in files if os.path.splitext(re.split(r'[\\/]', f)[-1])[0].lower() == stem and
                         not f.lower().endswith('.h')), None) or files[0]
            mpos = [mk[0] for mk in markers]

            def in_main(pos, _mk=markers, _mp=mpos, _main=main):
                i = bisect.bisect_right(_mp, pos) - 1
                return i >= 0 and _mk[i][2] == _main

            def orig_line(pos, _mk=markers, _mp=mpos):
                i = bisect.bisect_right(_mp, pos) - 1
                if i < 0:
                    return None
                return _mk[i][1] + P.text.count('\n', _mk[i][0], pos)
            seenf, inc_files = set(), []
            for f in files:
                if f not in seenf and f != main:
                    seenf.add(f); inc_files.append(f)
            marker_info = (main, inc_files, orig_line)
    P.run()
    funcs = P.funcs
    notes = list(P.notes)
    if asm_like:
        funcs = []
        P.globals_, P.types, P.protos, P.classes = [], [], [], []
        notes = ['Looks like an assembler include file (";" comments); only #define/#include lines extracted.']
    if in_main:
        funcs = [f for f in funcs if in_main(f['_pos']) and f['kind'] not in ('prototype',)]
        for f in funcs:
            ol = marker_info[2](f['_pos'])
            if ol:
                f['line'] = f"{ol} (of {re.split(r'[/\\\\]', marker_info[0])[-1]}; .i line {f['line']})"
        if len(funcs) > MAX_I_FUNCS:
            notes.append(f'{len(funcs)} functions found; list capped at {MAX_I_FUNCS}.')
            funcs = funcs[:MAX_I_FUNCS]
        P.globals_ = []
    # function-like macros
    incs, defs, macros, pragmas = c_outline(P)
    macro_funcs = []
    for fm, s, raw in macros[:400]:
        nm = fm.group(1)
        params = [(x.strip(), 'macro arg', '') for x in fm.group(2).split(',') if x.strip()]
        body = fm.group(3)
        sig = f'#define {nm}({fm.group(2)}) {body}'.strip()
        if len(sig) > 300:
            sig = sig[:300] + ' …'
        doc = P.doc_before(s) or P.doc_trailing(s, s + len(raw) + 200)
        calls = [re.sub(r'\s+', '', x) for x in CALL_RE.findall(body)]
        calls = list(dict.fromkeys(c for c in calls if c not in KEYWORDS and c != nm))[:30]
        macro_funcs.append({'name': nm, 'kind': 'macro', 'line': P.line_of(s), 'signature': sig,
                            'doc': strip_boiler(doc)[:MAX_DOC], 'params': params, 'returns': '', 'calls': calls, '_pos': s})
    if ext == 'i':
        macro_funcs = []
    if len(macros) > 400:
        notes.append(f'{len(macros)} function-like macros; first 400 listed.')
    allf = sorted(funcs + macro_funcs, key=lambda f: f['_pos'])
    if len(allf) > MAX_FUNCS:
        notes.append(f'{len(allf)} functions/macros found; list capped at {MAX_FUNCS}.')
        allf = allf[:MAX_FUNCS]
    for f in allf:
        f.pop('_pos', None)

    n_real_pre = [f for f in allf if f['kind'] not in ('macro', 'prototype', 'method declaration', 'abstract method')]
    outline = []
    if P.imports:
        outline.append({'heading': f'Imports ({len(P.imports)})'})
        outline += [f"`{i.replace('`', '')}`" for i in P.imports[:100]]
    if incs:
        outline.append({'heading': f'Includes ({len(incs)})'})
        outline += [f"`{i.replace('`', '')}`" for i in incs[:150]]
    if marker_info:
        outline.append({'heading': 'Preprocessed from'})
        outline.append(f"Main file: `{marker_info[0]}`")
        outline.append({'heading': f'Files merged by the preprocessor ({len(marker_info[1])})'})
        outline += [f"`{x}`" for x in marker_info[1][:120]]
    if defs:
        outline.append({'heading': f'Constants (#define, {len(defs)})'})
        for nm, val, ln, _ in defs[:80]:
            v = val.replace('`', '')
            if len(v) > 80:
                v = v[:80] + ' …'
            outline.append(f"`{nm}`" + (f" = `{v}`" if v else '') + f" (line {ln})")
        if len(defs) > 80:
            outline.append(f"… and {len(defs) - 80} more")
    if P.classes:
        outline.append({'heading': f'Classes ({len(P.classes)})'})
        outline += P.classes[:200]
    if P.types and ext != 'i':
        outline.append({'heading': f'Types ({len(P.types)})'})
        outline += P.types[:150]
        if len(P.types) > 150:
            outline.append(f"… and {len(P.types) - 150} more")
    if P.globals_:
        outline.append({'heading': f'Global variables / declarations ({len(P.globals_)})'})
        outline += P.globals_[:120]
        if len(P.globals_) > 120:
            outline.append(f"… and {len(P.globals_) - 120} more")
    defined = {f['name'] for f in allf}
    ext_protos = [n for n, _ in P.protos if n not in defined]
    if ext_protos:
        ext_protos = list(dict.fromkeys(ext_protos))
        outline.append({'heading': f'Prototypes declared but not defined here ({len(ext_protos)})'})
        outline.append(', '.join(f'`{n}`' for n in ext_protos[:200]) + (' …' if len(ext_protos) > 200 else ''))
    dead = []
    if ext != 'i':
        for s_, e_, tok in P.comments:
            if tok.count('\n') < 4 or '{' not in tok:
                continue
            for dm in DEAD_FN.finditer(tok):
                nm = dm.group(1)
                if nm not in KEYWORDS and nm not in dead:
                    dead.append(nm)
    if dead:
        dead_def = [d for d in dead if d not in defined]
        outline.append({'heading': f'Commented-out functions ({len(dead)})'})
        outline.append('Function bodies found inside comments (disabled code, not compiled): ' +
                       ', '.join(f'`{n}`' for n in dead[:150]) + (' …' if len(dead) > 150 else ''))
        if not n_real_pre:
            notes.append('All function bodies in this file are commented out (see Structure).')
    if pragmas and ext != 'i':
        outline.append({'heading': f'Pragmas ({len(pragmas)})'})
        outline += pragmas[:40]

    # summary
    summary, meta = '', []
    if P.header_used and P.header_text:
        summary, meta = header_summary(P.header_text)
    base_nm = os.path.basename(path).lower()
    if len(re.sub(r'[\W_]', '', summary.lower().replace(base_nm.rsplit('.', 1)[0], ''))) < 20:
        # trivial header (just the file name / revision): try the next descriptive comment
        first_fn = min([f['line'] for f in funcs if isinstance(f.get('line'), int)] or [10**9])
        for s_, e_, tok in P.comments[:12]:
            if P.line_of(s_) >= first_fn:
                break
            c_ = clean_comment(tok)
            if is_license(c_) or looks_like_code(c_):
                continue
            sm, mt = header_summary(c_)
            if len(re.sub(r'[\W_]', '', sm.lower().replace(base_nm.rsplit('.', 1)[0], ''))) >= 20:
                summary = sm
                meta = meta or mt
                break
    elif getattr(P, 'class_docs', None):
        summary, meta = header_summary(P.class_docs[0])
    DECL_KINDS = ('prototype', 'method declaration', 'abstract method')
    n_real = [f for f in allf if f['kind'] != 'macro' and f['kind'] not in DECL_KINDS]
    n_proto = [f for f in allf if f['kind'] in DECL_KINDS]
    n_mac = [f for f in allf if f['kind'] == 'macro']
    tname = TYPE_NAMES.get(ext, 'Source file')
    if lang == 'cpp' and ext in ('h', '_h'):
        tname = 'C++ header' + (' (backup copy)' if ext == '_h' else '')
    parts = []
    if n_real:
        nm = [f['name'] for f in n_real]
        parts.append(f"Defines {len(n_real)} function{'s' if len(n_real) != 1 else ''}: " +
                     ', '.join(nm[:12]) + (' …' if len(nm) > 12 else '') + '.')
    if n_proto:
        nm = [f['name'] for f in n_proto]
        parts.append(f"Declares {len(n_proto)} prototype{'s' if len(n_proto) != 1 else ''}: " +
                     ', '.join(nm[:12]) + (' …' if len(nm) > 12 else '') + '.')
    if n_mac:
        parts.append(f"{len(n_mac)} function-like macro{'s' if len(n_mac) != 1 else ''}.")
    if defs and not n_real:
        parts.append(f"{len(defs)} #define constant{'s' if len(defs) != 1 else ''}.")
    if not n_real and P.types:
        parts.append(f"{len(P.types)} type definition{'s' if len(P.types) != 1 else ''}.")
    if not n_real and P.globals_:
        gnames = [re.sub(r'\s*\(line \d+\)$', '', g).strip('`') for g in P.globals_[:6]]
        parts.append(f"{len(P.globals_)} global declaration{'s' if len(P.globals_) != 1 else ''} / data table{'s' if len(P.globals_) != 1 else ''}: "
                     + '; '.join(x[:60] for x in gnames) + (' …' if len(P.globals_) > 6 else '') + '.')
    if not n_real and P.classes:
        parts.append(f"{len(P.classes)} class/interface definition{'s' if len(P.classes) != 1 else ''}.")
    if not parts and not summary:
        parts.append(f"No function definitions ({len(P.lines):,} lines).")
    if summary:
        summary = summary.rstrip() + ('' if summary.rstrip().endswith(('.', '…')) else '.') + ' ' + ' '.join(parts)
    elif parts:
        summary = f"{tname}. " + ' '.join(parts)
    if ext == 'i' and marker_info:
        if summary.startswith(tname + '. '):
            summary = summary[len(tname) + 2:]
        summary = (f"Compiler-preprocessed output of `{re.split(r'[/\\\\]', marker_info[0])[-1]}` "
                   f"(headers expanded inline). " + summary)
    meta = [('Language', {'c': 'C', 'cpp': 'C++', 'java': 'Java', 'csharp': 'C#', 'javascript': 'JavaScript',
                          'idl': 'IDL'}.get(lang, lang))] + meta
    meta.append(('Lines', f'{len(P.lines):,}'))
    if n_real:
        meta.append(('Functions defined', len(n_real)))
    # comments as full text
    ctexts = []
    if ext != 'i':
        ctexts = [clean_comment(c[2]) for c in P.comments]
    else:
        ctexts = [clean_comment(c[2]) for c in P.comments if in_main and in_main(c[0])] if in_main else []
    # merge consecutive // lines into paragraphs
    merged, buf, last_e = [], [], None
    for (s, e, tok), ct in zip([c for c in P.comments if ext != 'i' or (in_main and in_main(c[0]))], ctexts):
        if tok.startswith('//') and buf and last_e is not None and P.text.count('\n', last_e, s) <= 1 and \
                not P.masked[last_e:s].strip():
            buf.append(ct)
        else:
            if buf:
                merged.append('\n'.join(buf))
            buf = [ct]
        last_e = e
    if buf:
        merged.append('\n'.join(buf))
    pars = comment_paragraphs(merged)
    if pars:
        pars = [{'heading': 'Source comments'}] + pars
    fnames = [f['name'] for f in n_real] or [f['name'] for f in allf]
    kws = chips_keywords(text, fnames, [i.strip('<>"') for i in incs if not re.search(r'std|string|math|ctype|stdio|stdlib', i)][:3])
    return {'kind': 'source', 'type': tname, 'summary': summary, 'keywords': kws, 'meta': meta,
            'functions': allf, 'outline': outline, 'code_lang': lang, 'notes': notes, 'paragraphs': pars}


# ------------------------------------------------------------------ Visual Basic
VB_PROC = re.compile(r'^\s*((?:(?:Public|Private|Friend|Protected|Shared|Static|Overrides|Overridable|'
                     r'Overloads|MustOverride|NotOverridable|Shadows|Partial|Async|Iterator|Default|ReadOnly|WriteOnly)\s+)*)'
                     r'(Sub|Function|Property\s+(?:Get|Let|Set)|Property|Operator|Event)\s+([\w\[\]]+)\s*(\((.*?)\))?\s*(.*)$', re.I)
VB_DECL = re.compile(r'^\s*(?:(?:Public|Private)\s+)?Declare\s+(?:PtrSafe\s+)?(?:Ansi\s+|Unicode\s+|Auto\s+)?'
                     r'(Sub|Function)\s+(\w+)\s+Lib\s+"([^"]*)"(?:\s+Alias\s+"([^"]*)")?\s*(\((.*)\))?\s*(.*)$', re.I)
VB_END = re.compile(r'^\s*End\s+(Sub|Function|Property|Operator|Event)\b', re.I)
VB_CONT = re.compile(r'^\s*((?:(?:Public|Private|Friend|Protected|Partial|Shared|MustInherit|NotInheritable)\s+)*)'
                     r'(Class|Module|Structure|Interface|Namespace|Enum|Type)\s+(\w+)', re.I)
VB_KW = set("""if then else elseif end for next each while wend do loop until select case with call dim redim
set let get goto gosub return exit on error resume new not and or xor mod is like to step as byval byref
optional paramarray preserve nothing true false me mybase myclass integer long string boolean double single
variant object byte date currency decimal print open close input output append binary random line chr chr$
len left right mid mid$ left$ right$ trim val str str$ cint clng cstr cdbl csng cbool cbyte ubound lbound
format format$ instr asc hex hex$ isnull isempty isnumeric doevents msgbox inputbox array split join replace
abs int fix sgn sqr rnd timer now lcase ucase lcase$ ucase$ space space$ string$ typeof addressof""".split())


def vb_strip(line):
    """Remove a trailing ' comment from a VB line (respecting strings); return (code, comment)."""
    in_s = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_s = not in_s
        elif ch == "'" and not in_s:
            return line[:i], line[i + 1:]
    m = re.match(r'^(\s*)Rem\b(.*)$', line, re.I)
    if m and not in_s:
        return '', m.group(2)
    return line, None


def extract_vb(path, text, ext):
    raw_lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    outline, controls, attrs = [], [], {}
    # skip classic VB designer block
    start = 0
    if ext in ('frm', 'ctl', 'cls') or (raw_lines and raw_lines[0].startswith('VERSION ')):
        depth = 0
        for i, ln in enumerate(raw_lines):
            s = ln.strip()
            mb = re.match(r'^Begin\s+([\w.]+)\s+(\w+)', s)
            if mb:
                depth += 1
                controls.append((mb.group(1), mb.group(2), depth))
            elif re.match(r'^End$', s) and depth:
                depth -= 1
            ma = re.match(r'^Attribute\s+(\w+)\s*=\s*(.*)$', s)
            if ma:
                attrs[ma.group(1)] = ma.group(2).strip('"')
                start = i + 1
            elif depth == 0 and s and not s.startswith(('VERSION', 'Object', 'Begin', 'End', 'BeginProperty', 'EndProperty')) and i > 0 and not mb:
                if not attrs and not re.match(r'^(Option|Public|Private|Dim|Const|Sub|Function|\')', s, re.I):
                    continue
                if attrs or re.match(r'^(Option|Public|Private|Dim|Const|Sub|Function|\')', s, re.I):
                    if not start:
                        start = i
                    break
    # join continuation lines, keep original line numbers
    logical = []
    i = start
    while i < len(raw_lines):
        ln, ln0 = raw_lines[i], i + 1
        code, com = vb_strip(ln)
        coms = [com] if com is not None else []
        while code.rstrip().endswith(' _') and i + 1 < len(raw_lines):
            i += 1
            c2, cm2 = vb_strip(raw_lines[i])
            code = code.rstrip()[:-1] + ' ' + c2.strip()
            if cm2 is not None:
                coms.append(cm2)
        logical.append((ln0, code, coms))
        i += 1
    funcs, scope, globals_, consts, pend_com = [], [], [], [], []
    cur = None
    known = set()
    for ln0, code, coms in logical:
        code = re.sub(r'^\s*(?:<[^<>]*(?:<[^<>]*>[^<>]*)*>\s*)+', '', code)
        m = VB_PROC.match(code) or VB_DECL.match(code)
        if m and m.re is VB_PROC and not re.match(r'^\s*(Exit|End)\b', code, re.I):
            known.add(m.group(3).lower())
        elif m and m.re is VB_DECL:
            known.add(m.group(2).lower())
    comments_all = []
    for ln0, code, coms in logical:
        s = re.sub(r'^(?:<[^<>]*(?:<[^<>]*>[^<>]*)*>\s*)+', '', code.strip())
        comtxt = ' '.join(c.strip() for c in coms).strip()
        if comtxt:
            comments_all.append((ln0, comtxt))
        if cur is not None:
            if VB_END.match(s):
                cur['_end'] = ln0
                funcs.append(cur); cur = None
                pend_com = []
                continue
            if not cur['doc'] and comtxt and not cur['_body']:
                cur['doc'] = comtxt
            if s:
                cur['_body'].append(s)
            continue
        if not s:
            if not comtxt:
                pend_com = []
            else:
                pend_com.append(comtxt)
            continue
        mc = VB_CONT.match(s)
        if mc and not re.match(r'^\s*End\b', s, re.I):
            kw, nm = mc.group(2), mc.group(3)
            if kw.lower() in ('enum', 'type', 'structure'):
                outline.append(f"{kw} `{nm}` (line {ln0})")
            if kw.lower() in ('class', 'module', 'namespace', 'interface', 'structure'):
                scope.append(nm)
                outline.append(f"{kw} `{'.'.join(scope)}` (line {ln0})")
            pend_com = []
            continue
        if re.match(r'^End\s+(Class|Module|Namespace|Interface|Structure)\b', s, re.I) and scope:
            scope.pop(); continue
        md = VB_DECL.match(s)
        if md:
            params = vb_params(md.group(6) or '')
            funcs.append({'name': md.group(2), 'kind': 'declare (DLL import)', 'line': ln0, 'signature': _norm(s),
                          'doc': ' '.join(pend_com) or comtxt or f'Imported from {md.group(3)}' + (f' (alias {md.group(4)})' if md.group(4) else ''),
                          'params': params, 'returns': vb_as(md.group(7)), 'calls': []})
            pend_com = []
            continue
        mp = VB_PROC.match(s)
        if mp and not re.match(r'^(Exit|End)\b', s, re.I):
            kind = mp.group(2).lower()
            kind = re.sub(r'\s+', ' ', kind)
            kind = {'sub': 'sub', 'function': 'function'}.get(kind, kind)
            mods = mp.group(1).lower()
            nm = mp.group(3)
            if re.match(r'^\w+_(Click|Load|Change|Timer|KeyPress|KeyDown|KeyUp|MouseDown|MouseUp|MouseMove|'
                        r'OnComm|Unload|Resize|Activate|GotFocus|LostFocus|DblClick|Initialize|Terminate|Paint|Scroll|DataArrival|Connect|Error)$', nm):
                kind = 'event handler'
            ret = vb_as(mp.group(6))
            hm = re.search(r'\bHandles\s+([\w.,\s]+)', mp.group(6) or '', re.I)
            if hm:
                kind = 'event handler'
            full = '.'.join(scope + [nm]) if scope else nm
            if ext in ('cls', 'frm', 'ctl') and not scope and attrs.get('VB_Name'):
                full = attrs['VB_Name'] + '.' + nm
            if nm.lower() == 'new' and kind == 'sub':
                kind = 'constructor'
            cur = {'name': full, 'kind': kind, 'line': ln0, 'signature': _norm(s),
                   'doc': ' '.join(pend_com) or comtxt, 'params': vb_params(mp.group(5) or ''),
                   'returns': ret, 'calls': [], '_body': []}
            if 'mustoverride' in mods or (scope and False):
                cur['_end'] = ln0; funcs.append(cur); cur = None
            pend_com = []
            continue
        if not scope or True:
            mv = re.match(r'^(?:(Public|Private|Global|Dim|Friend|Protected|Shared)\s+)+(?:(Const)\s+)?(?:WithEvents\s+)?(\w+)', s, re.I)
            if mv and not re.match(r'^\s*(Public|Private)\s+(Sub|Function|Property|Declare|Enum|Type|Class|Module|Event)\b', s, re.I):
                if mv.group(2) or re.match(r'^Const\b', s, re.I):
                    consts.append(f"`{_norm(s)[:140]}` (line {ln0})")
                else:
                    globals_.append(f"`{_norm(s)[:140]}` (line {ln0})")
            elif re.match(r'^Const\s+', s, re.I):
                consts.append(f"`{_norm(s)[:140]}` (line {ln0})")
        pend_com = []
    if cur is not None:
        funcs.append(cur)
    for f in funcs:
        body = ' '.join(f.pop('_body', []))
        f.pop('_end', None)
        body = re.sub(r'"[^"]*"', '""', body)
        calls = []
        for mm in re.finditer(r'\bCall\s+([\w.]+)|\b([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*(\()?', body):
            nm = mm.group(1) or mm.group(2)
            if not nm:
                continue
            nm = re.sub(r'^Me\.', '', nm, flags=re.I)
            base = nm.split('.')[-1].lower()
            if mm.group(1) or base in known or (mm.group(3) and '.' in nm and base not in VB_KW):
                if nm.lower() not in VB_KW and nm not in calls:
                    calls.append(nm)
            if len(calls) >= MAX_CALLS:
                break
        f['calls'] = calls
        f['doc'] = f['doc'][:MAX_DOC]
    if attrs.get('VB_Name'):
        outline.insert(0, f"VB_Name: `{attrs['VB_Name']}`")
    if controls:
        outline.append({'heading': f'Form controls ({len(controls)})'})
        outline += [f"{'  ' * 0}`{n}` ({t})" for t, n, d in controls[:200]]
    if consts:
        outline.append({'heading': f'Constants ({len(consts)})'})
        outline += consts[:80]
    if globals_:
        outline.append({'heading': f'Module-level variables ({len(globals_)})'})
        outline += globals_[:120]
    # header comment = comments before first code line
    first_code = next((ln0 for ln0, code, coms in logical if code.strip() and not re.match(r'^\s*Option\b', code, re.I)), 10**9)
    head = [c for ln0, c in comments_all if ln0 < first_code]
    summary, meta = ('', [])
    if head:
        summary, meta = header_summary('\n'.join(head))
    tname = TYPE_NAMES.get(ext, 'Visual Basic source')
    real = [f for f in funcs if not f['kind'].startswith('declare')]
    part = ''
    if real:
        part = f"Defines {len(real)} procedure{'s' if len(real) != 1 else ''}: " + ', '.join(f['name'] for f in real[:12]) + (' …' if len(real) > 12 else '') + '.'
    if controls:
        part += f" Form with {len(controls)} controls."
    summary = (summary + ' ' + part).strip() if summary else (f'{tname}. ' + part if part else '')
    pars = comment_paragraphs([c for _, c in comments_all])
    if pars:
        pars = [{'heading': 'Source comments'}] + pars
    meta = [('Language', 'VB.NET' if ext == 'vb' else 'Visual Basic 6')] + meta + [('Lines', f'{len(raw_lines):,}')]
    kws = chips_keywords(text, [f['name'] for f in real], [attrs.get('VB_Name', '')])
    return {'kind': 'source', 'type': tname, 'summary': summary, 'keywords': kws, 'meta': meta,
            'functions': funcs[:MAX_FUNCS], 'outline': outline, 'code_lang': 'vbnet' if ext == 'vb' else 'vb',
            'paragraphs': pars}


def vb_as(s):
    m = re.match(r'^\s*As\s+(?:New\s+)?([\w.()]+(?:\(\))?)', s or '', re.I)
    return m.group(1) if m else ''


def vb_params(s):
    out = []
    for p in CParser._split_top(s):
        if not p:
            continue
        m = re.match(r'^((?:(?:Optional|ByVal|ByRef|ParamArray)\s+)*)(\w+)(\(\))?\s*(?:As\s+(?:New\s+)?([\w.]+))?\s*(?:=\s*(.*))?$', p, re.I)
        if m:
            t = (m.group(4) or 'Variant' if True else '') + ('()' if m.group(3) else '')
            mods = m.group(1).strip()
            out.append((m.group(2), (mods + ' ' if mods else '') + t + (f' = {m.group(5)}' if m.group(5) else ''), ''))
        else:
            out.append(('(param)', p, ''))
    return out


# ------------------------------------------------------------------ Python
def extract_py(path, text, ext):
    funcs, outline, pars, notes = [], [], [], []
    summary = ''
    lines = text.split('\n')
    try:
        tree = ast.parse(text)
    except Exception:
        tree = None
    if tree is not None:
        mod_doc = ast.get_docstring(tree) or ''

        def visit(node, prefix, in_class):
            for ch in ast.iter_child_nodes(node):
                if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = '.'.join(prefix + [ch.name])
                    a = ch.args
                    params = []
                    posargs = list(getattr(a, 'posonlyargs', [])) + list(a.args)
                    defs = [None] * (len(posargs) - len(a.defaults)) + list(a.defaults)
                    for arg, d in zip(posargs, defs):
                        t = ast.unparse(arg.annotation) if arg.annotation is not None and hasattr(ast, 'unparse') else ''
                        if d is not None and hasattr(ast, 'unparse'):
                            t = (t + ' ' if t else '') + '= ' + ast.unparse(d)
                        params.append((arg.arg, t, ''))
                    if a.vararg:
                        params.append(('*' + a.vararg.arg, 'varargs', ''))
                    for arg in a.kwonlyargs:
                        params.append((arg.arg, 'keyword-only', ''))
                    if a.kwarg:
                        params.append(('**' + a.kwarg.arg, 'kwargs', ''))
                    calls = []
                    for n in ast.walk(ch):
                        if isinstance(n, ast.Call):
                            try:
                                c = ast.unparse(n.func) if hasattr(ast, 'unparse') else getattr(n.func, 'id', '')
                            except Exception:
                                c = ''
                            c = re.sub(r'^self\.', '', c)
                            if c and len(c) < 60 and '(' not in c and c not in calls:
                                calls.append(c)
                    sig = lines[ch.lineno - 1].strip() if ch.lineno - 1 < len(lines) else 'def ' + ch.name
                    if not sig.rstrip().endswith(':'):
                        k = ch.lineno
                        while k < len(lines) and k < ch.lineno + 15 and not sig.rstrip().endswith(':'):
                            sig += ' ' + lines[k].strip(); k += 1
                    doc = ast.get_docstring(ch) or ''
                    if not doc:
                        j = ch.lineno - 2 - len(ch.decorator_list)
                        cm = []
                        while j >= 0 and lines[j].strip().startswith('#'):
                            cm.insert(0, lines[j].strip().lstrip('#').strip()); j -= 1
                        doc = '\n'.join(cm)
                    ret = ast.unparse(ch.returns) if ch.returns is not None and hasattr(ast, 'unparse') else ''
                    kind = 'method' if in_class else 'function'
                    if in_class and ch.name == '__init__':
                        kind = 'constructor'
                    funcs.append({'name': name, 'kind': kind, 'line': ch.lineno, 'signature': _norm(sig),
                                  'doc': doc[:MAX_DOC], 'params': params, 'returns': ret, 'calls': calls[:MAX_CALLS]})
                    visit(ch, prefix + [ch.name], False)
                elif isinstance(ch, ast.ClassDef):
                    bases = ', '.join(ast.unparse(b) for b in ch.bases) if hasattr(ast, 'unparse') else ''
                    d = (ast.get_docstring(ch) or '').split('\n')[0]
                    outline.append(f"class `{'.'.join(prefix + [ch.name])}`" + (f"({bases})" if bases else '') +
                                   f" (line {ch.lineno})" + (f" — {d}" if d else ''))
                    visit(ch, prefix + [ch.name], True)
        visit(tree, [], False)
        imps = []
        for n in tree.body:
            if isinstance(n, ast.Import):
                imps += [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                imps.append((n.module or '.') + ' (' + ', '.join(a.name for a in n.names) + ')')
        if imps:
            outline = [{'heading': 'Imports'}] + [f'`{i}`' for i in imps] + ([{'heading': 'Classes'}] if outline else []) + outline
        if mod_doc:
            summary, _ = header_summary(mod_doc)
    else:
        notes.append('Not valid Python 3 (probably Python 2); parsed with a line-based fallback.')
        stack = []
        for i, ln in enumerate(lines, 1):
            m = re.match(r'^(\s*)(def|class)\s+(\w+)\s*(\(([^)]*)\))?', ln)
            if not m:
                continue
            ind = len(m.group(1).expandtabs())
            while stack and stack[-1][0] >= ind:
                stack.pop()
            if m.group(2) == 'class':
                outline.append(f"class `{'.'.join([s[1] for s in stack] + [m.group(3)])}` (line {i})")
                stack.append((ind, m.group(3), True))
                continue
            in_cls = bool(stack and stack[-1][2])
            name = '.'.join([s[1] for s in stack] + [m.group(3)])
            params = [(p.strip().split('=')[0].strip(), ('= ' + p.split('=', 1)[1].strip()) if '=' in p else '', '')
                      for p in (m.group(5) or '').split(',') if p.strip()]
            doc = ''
            if i < len(lines):
                dm = re.match(r'^\s*[rRuU]?("""|\'\'\'|"|\')(.*)', lines[i])
                if dm:
                    doc = dm.group(2).split(dm.group(1))[0].strip()
            body = []
            for ln2 in lines[i:i + 2000]:
                if ln2.strip() and len(ln2) - len(ln2.lstrip()) <= ind and not ln2.strip().startswith('#'):
                    break
                body.append(re.sub(r'#.*$|"[^"\n]*"|\'[^\'\n]*\'', '', ln2))
            calls = []
            for cm in re.finditer(r'(?<![\w.])([A-Za-z_][\w.]*)\s*\(', '\n'.join(body)):
                c = re.sub(r'^self\.', '', cm.group(1))
                if c.split('.')[-1] not in KEYWORDS and c not in calls:
                    calls.append(c)
            funcs.append({'name': name, 'kind': 'method' if in_cls else 'function', 'line': i,
                          'signature': ln.strip(), 'doc': doc, 'params': params, 'returns': '', 'calls': calls[:MAX_CALLS]})
            stack.append((ind, m.group(3), False))
    if not summary:
        head = []
        for ln in lines[:60]:
            s = ln.strip()
            if s.startswith('#!') or re.match(r'#.*coding[:=]', s):
                continue
            if s.startswith('#'):
                head.append(s.lstrip('#').strip())
            elif s:
                break
        if head:
            summary, _ = header_summary('\n'.join(head))
    real = funcs
    part = (f"Defines {len(real)} function{'s' if len(real) != 1 else ''}: " + ', '.join(f['name'] for f in real[:12]) +
            (' …' if len(real) > 12 else '') + '.') if real else ''
    summary = (summary.rstrip() + ' ' + part).strip() if summary else ('Python source. ' + part if part else '')
    coms = [l.strip().lstrip('#').strip() for l in lines if l.strip().startswith('#') and not l.startswith('#!')]
    pars = comment_paragraphs(['\n'.join(coms)] if coms else [])
    if pars:
        pars = [{'heading': 'Source comments'}] + pars
    kws = chips_keywords(text, [f['name'] for f in funcs])
    return {'kind': 'source', 'type': 'Python source', 'summary': summary, 'keywords': kws,
            'meta': [('Language', 'Python'), ('Lines', f'{len(lines):,}')], 'functions': funcs[:MAX_FUNCS],
            'outline': outline, 'code_lang': 'python', 'notes': notes, 'paragraphs': pars}


# ------------------------------------------------------------------ entry
def _read(path):
    with open(path, 'rb') as f:
        data = f.read(20_000_001)
    trunc = len(data) > 20_000_000
    data = data[:20_000_000]
    for enc in ('utf-8', 'cp1252', 'latin-1'):
        try:
            return data.decode(enc), trunc
        except UnicodeDecodeError:
            continue
    return data.decode('latin-1', 'replace'), trunc


def extract(path):
    name = os.path.basename(path).lower()
    ext = name.rsplit('.', 1)[1] if '.' in name else ''
    try:
        if os.path.getsize(path) == 0:
            return {'kind': 'source', 'type': TYPE_NAMES.get(ext, 'Source file'),
                    'summary': f"Empty {TYPE_NAMES.get(ext, 'source file')} (0 bytes).", 'notes': ['Empty file.']}
        text, trunc = _read(path)
        if text.count('\x00') > len(text) // 20:
            return {'kind': 'binary', 'type': TYPE_NAMES.get(ext, 'Source file') + ' (binary content)',
                    'notes': ['File has a source-code extension but contains binary data.']}
        text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\x00', '').lstrip('\ufeff')
        lang = LANG_OF.get(ext, 'c')
        if lang in ('vb', 'vbnet'):
            r = extract_vb(path, text, ext)
        elif lang == 'python':
            r = extract_py(path, text, ext)
        else:
            r = extract_c(path, text, ext)
        if trunc:
            r.setdefault('notes', []).append('File larger than 20 MB: only the first 20 MB parsed.')
        if not r.get('notes'):
            r.pop('notes', None)
        return r
    except Exception as e:      # never raise: return what we can
        try:
            text, _ = _read(path)
            return {'kind': 'source', 'type': TYPE_NAMES.get(ext, 'Source file'),
                    'paragraphs': [p for p in re.split(r'\n\s*\n', text[:2_000_000]) if p.strip()],
                    'notes': [f'csource parser failed ({type(e).__name__}: {str(e)[:100]}); raw text shown.']}
        except Exception:
            return {'kind': 'source', 'type': TYPE_NAMES.get(ext, 'Source file'),
                    'notes': [f'csource parser failed ({type(e).__name__}).']}
