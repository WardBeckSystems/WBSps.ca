"""Assembly, compiler/assembler listings, linker scripts/maps and firmware images.

Handles: PIC MPASM, Atmel AVR (Atmel asm + ImageCraft ICCAVR compiler output),
8051, ADI SHARC / ADSP-21xx / Blackfin, GNU as / ARM / XMOS, IAR; listings
(.lis/.lst); linker maps (GNU, MPLINK, XC8, ADI) plus doxygen image maps and
Xilinx/Quartus text reports that share the .map extension; linker scripts
(.ld/.lds/.ldf/.icf/.xcl/.lk); Intel HEX and Motorola S-records; and the
non-assembly look-alikes that share these extensions in the archive (Altera
AHDL .inc prototypes, Xilinx/Altera .sym schematic symbols, ImageCraft .src
project lists, IAR C-SPY .mac macro files).
"""
import os, re, collections

import core

EXTS = {'s', '_s', 'asm', 'a51', 's79', 's43', 'inc', 'mac', 'src', 'lis', 'lst', 'map', 'lk', 'ld',
        'lds', 'ldf', 'icf', 'xcl', 'hex', 'ihx', 'srec', 's19', 's28', 's37', 'dsp', 'sym'}

MAX_PARS_CHARS = 400_000
MAX_FUNCS = 1500


# ====================================================================== entry
def extract(path):
    try:
        return _extract(path)
    except Exception as e:  # never raise
        try:
            r = _generic(path)
        except Exception:
            r = {'kind': 'binary'}
        r.setdefault('notes', []).append(f'asm extractor internal error ({type(e).__name__}: {str(e)[:100]}); generic text used.')
        return r


def _ext(path):
    n = os.path.basename(path).lower()
    return n.rsplit('.', 1)[1] if '.' in n else ''


def _generic(path, text=None, kind='document', typ=None, notes=None):
    if text is None:
        if core.looks_binary(path):
            return _binary(path)
        text, trunc = core.read_text(path)
        notes = (notes or []) + (['File larger than 20 MB: text truncated.'] if trunc else [])
    notes = list(notes or [])
    r = {'kind': kind, 'paragraphs': _cap_pars(core.split_paragraphs(text), notes)}
    if typ:
        r['type'] = typ
    if notes:
        r['notes'] = notes
    return r


def _binary(path, typ=None):
    with open(path, 'rb') as f:
        data = f.read(4_000_000)
    strs = _strings(data)
    r = {'kind': 'binary', 'type': typ or 'binary file',
         'meta': [('First bytes', '`' + data[:16].hex(' ') + '`')],
         'notes': ['Binary file: only printable strings were extracted.']}
    if strs:
        r['outline'] = [{'heading': f'Printable strings ({len(strs)})'}] + [f'`{s}`' for s in strs[:150]]
    return r


def _strings(data, n=4, strict=False):
    out, seen = [], set()
    for m in re.finditer(rb'[\x20-\x7e]{%d,}' % n, data):
        s = m.group(0).decode('ascii').strip()
        if len(s) < n or s in seen or sum(c.isalnum() for c in s) < n - 1:
            continue
        if strict:
            letters = sum(c.isalpha() or c == ' ' for c in s) / len(s)
            if letters < 0.7 or not re.search(r'[A-Za-z]{3,}', s) or len(set(s)) < 4 or sum(c in '"%$&*#@^~`|\\{}<>' for c in s) > 1:
                continue
            if not (re.search(r'[aeiouAEIOU]', s) and (' ' in s or re.search(r'[a-z]{3}|[A-Z]{2,}\d|\d[A-Z]', s))):
                continue
        seen.add(s); out.append(s.replace('`', "'")[:100])
    return out


def _cap_pars(pars, notes):
    out, n = [], 0
    for p in pars:
        if isinstance(p, str):
            n += len(p)
            if n > MAX_PARS_CHARS:
                notes.append(f'Text capped at {MAX_PARS_CHARS:,} characters in this sidecar.')
                break
        out.append(p)
    return out


def _read(path):
    text, trunc = core.read_text(path)
    return text.replace('\r\n', '\n').replace('\r', '\n'), trunc


def _extract(path):
    ext = _ext(path)
    if ext in ('hex', 'ihx', 'srec', 's19', 's28', 's37'):
        return _firmware(path, ext)
    if ext == 'sym':
        return _sym(path)
    if core.looks_binary(path):
        return _binary(path)
    text, trunc = _read(path)
    notes = ['File larger than 20 MB: text truncated.'] if trunc else []
    head = text[:4000]
    if ext == 'map':
        return _map(path, text, notes)
    if ext in ('ld', 'lds', 'ldf', 'icf', 'xcl', 'lk'):
        return _linker_script(path, text, ext, notes)
    if ext in ('lis', 'lst'):
        return _listing(path, text, notes)
    if ext == 'inc' and re.search(r'^\s*FUNCTION\s+\w+\s*\(.*?\bRETURNS\b|^\s*define\s+\w+\s*\([^)]*\)\s*=', text, re.M | re.I | re.S):
        return _ahdl_inc(path, text, notes)
    if ext == 'inc' and re.search(r'^\s*(--|library\s+ieee|entity\s|component\s)', head, re.M | re.I) \
            and not re.search(r'^\s*[;#.]', head, re.M):
        return _generic(path, text, typ='HDL include file (VHDL/AHDL)', notes=notes)
    if ext == 'src' and re.match(r'\s*\[(Files|source|Headers)\]', head, re.I):
        return _icc_project(path, text, notes)
    if ext == 'src' and re.search(r'^\s*#\s*@\(#\)|^\w[\w.]*\s*=\s*', head, re.M) and not _asm_like(head):
        return _generic(path, text, typ='properties / text file', notes=notes)
    if ext == 'mac' and not re.search(r'^\s*\w+\s+MACRO\b|^\s*\.macro\b', text, re.M) and re.search(r'^\s*\w+\s*\([^;{]*\)\s*\n?\s*\{', text, re.M):
        return _cspy_mac(path, text, notes)
    if ext == 'dsp' and re.search(r'^#\s*Microsoft Developer Studio|^# Microsoft', head, re.M):
        return _generic(path, text, typ='Microsoft Developer Studio project', notes=notes)
    if not _asm_like(text[:200000]):
        return _generic(path, text, notes=notes)
    return _asm(path, text, notes)


def _asm_like(t):
    return bool(re.search(r'^\s*(\.?(section|segment|text|data|global|globl|org|module|area|equ|include|macro|byte|word)\b'
                          r'|\w+:|#include|#\s*define|[A-Za-z_]\w*\s+(EQU|MACRO|RES|SET)\b|\s+(movlw|movwf|ldi|mov|call|rcall|jmp|ret|rts|goto|ld|st|add|sub)\b)',
                          t, re.M | re.I))


# ====================================================================== assembly
DIALECTS = [
    ('imagecraft', 'ImageCraft ICCAVR compiler output (AVR assembly)', r'^\s*\.dbfunc\b|^\s*\.module\s+\S+\.c\b', 50),
    ('xmos', 'XMOS XS1 compiler assembly output', r'\.cc_top\b|\bentsp\b|\bretsp\b', 20),
    ('pic', 'Microchip PIC MPASM assembly', r'\b(movlw|movwf|movf|btfss|btfsc|bsf|bcf|decfsz|incfsz|retlw|retfie|clrwdt|banksel|pagesel)\b|__CONFIG|\bLIST\s+P\s*=|ERRORLEVEL|#include\s*[<"]p1[0-9]', 1),
    ('avr', 'Atmel AVR assembly', r'\b(rjmp|rcall|ldi|sbi|cbi|brne|breq|lpm|spm|sbrs|sbrc|sbis|sbic|adiw|sbiw|lds|sts)\b|\.include\s+"m\d+\w*def\.inc"|\.cseg\b|\.dseg\b|\.eseg\b', 1),
    ('8051', 'Intel 8051 assembly', r'\b(lcall|acall|ljmp|sjmp|ajmp|movx|movc|djnz|cjne|setb)\b|\bdptr\b|\bCSEG\s+AT\b', 1),
    ('blackfin', 'ADI Blackfin assembly', r'\[\s*--\s*SP\s*\]|\bP[0-5]\.[LH]\b|\bCSYNC\b|\bSSYNC\b|\bLINK\s+\d+\s*;|\bUNLINK\b|def[Bb][Ff]\d', 3),
    ('sharc', 'ADI SHARC (ADSP-21xxx) assembly', r'\.section\s*/\s*(pm|dm)\b|\.segment\s*/\s*(pm|dm)\b|\.endseg\b|\b(dm|pm)\s*\(\s*\w+\s*,|\blcntr\s*=|\brts\s*\(\s*db\s*\)|\bustat\d\b|def210\d\d|def2116|def2126|def2136|\bbit\s+set\s+\w+', 2),
    ('adsp21xx', 'ADI ADSP-21xx (16-bit) assembly', r'^\s*\.MODULE\b|^\s*\.ENDMOD\b|\b(AX0|AY0|MX0|MY0|SR1|SR0|MR1)\b|\bCNTR\s*=', 2),
    ('arm', 'ARM assembly', r'\b(stmfd|ldmfd|stmdb|ldmia|bx|blx|mrs|msr|cpsie|cpsid|ldr|str)\b|^\s+bl\s+\w|\bpush\s*\{|\bpop\s*\{|^\s*(AREA|THUMB|CODE32|PRESERVE8)\b|\.thumb\b|\.arm\b|\.syntax\s+unified', 1),
    ('msp430', 'TI MSP430 assembly', r'\b(mov|add|bis|bic|push|pop|cmp|tst)\.(w|b|a)\b|\bcall[a]?\s+#\w|\bpushm\.|\bpopm\.|\bdint\b|\beint\b', 2),
    ('renesas', 'Renesas (SuperH / RX) assembly', r'^\s*\.(SECTION|EXPORT|IMPORT|GLB)\b|\bMOV\.L\b|\bRTS/N\b|\bRTE\b', 1),
    ('m68k', 'Motorola 68k / ColdFire assembly', r'\bmove\.l\b|\bmovem\.l\b|\blea\b.*\(\s*%?a[0-7]\s*\)|\bjsr\b', 1),
]

SKIP_BACK = re.compile(r'^\s*(\.?(global|globl|globa|public|export|type|align|even|func|ent|extern|weak|thumb_func|size|section|text|area|cc_top|dbfunc)\b|#\s*define\b|PUBLIC\b|GLOBAL\b|EXPORT\b|RSEG\b|ALIGN\b|THUMB\b|ARM\b|CODE\b)', re.I)

CALL_RE = re.compile(r'(?<![\w.])(call|rcall|xcall|lcall|acall|icall_?|jsr|bsr|bl|blx|bla|jal|calla|callr|scall|fcall|_call)\b\s*(?:\(\s*pc\s*,\s*)?#?\s*([A-Za-z_.$?@][\w.$?@]*)', re.I)
JUMP_RE = re.compile(r'(?<![\w.])(goto|rjmp|jmp|ljmp|ajmp|sjmp|b|bra|jump|br|j)\b\s*(?:\(\s*pc\s*,\s*)?#?\s*([A-Za-z_.$?@][\w.$?@]*)', re.I)
RET_RE = re.compile(r'(?<![\w.])(return|retlw|retfie|reti|ret|rts|rti|rte|retsp|iret|eret|retn|rtd|rts/n)\b|\bbx\s+lr\b|\bpop\s*\{[^}]*\bpc\b|\bldm\w*\s+sp!?\s*,\s*\{[^}]*\bpc\b|\bmov\s+pc\s*,\s*lr\b|\bmovs\s+pc\s*,\s*lr\b|\bsubs\s+pc\s*,\s*lr\b|\bRETURN\b|\bleaf_exit\b|^\s*exit\s*;', re.I)
REGS = re.compile(r'^(r\d+|lr|pc|sp|ip|fp|w\d*|x|y|z|a|b|c|dptr|acc|@\w+|i\d+|m\d+|p\d|\(.*)$', re.I)

DIRECTIVE_WORDS = set("""org end list nolist errorlevel include title subtitle processor radix cblock endc equ set macro endm
exitm local if ifdef ifndef else endif while endw __config __idlocs __badram __maxram config db dw dt de ds data res
fill space page expand noexpand messg error variable constant code udata udata_shr udata_acs idata extern global
banksel pagesel bankisel cseg dseg xseg iseg bseg rseg segment ends assume proc endp public extrn name using area
section rseg common module endmod thumb arm preserve8 require8 import export align dcd dcb dcw spc define ltorg
""".split())

LOCAL_RE = re.compile(r'^(\.|\$|@|\?|\d+$|L\d+$|X\d+$|\.?L[A-Za-z_]*\d+$|\.?Ltmp|\.?Lfunc|\.?Lxta|__?L\d+$)')
VEC_NAME = re.compile(r'(^|_)(isr|irq|fiq|interrupt|handler|vector|vectors|trap|swi|nmi)(_|$|\d)|isr$|irq$|handler$|_int\d*$|^int\d+$|^_?int_', re.I)
IRET_RE = re.compile(r'(?<![\w.])(retfie|reti|rti|rte|iret|eret)\b|\bsubs\s+pc\s*,\s*lr\b', re.I)
ENTRY_NAME = re.compile(r'^_?_?(main|start|_start|reset|reset_handler|startup|cstartup|init|boot|entry|begin|pre_main|power_?on)$', re.I)

INC_RE = re.compile(r'^\s*(?:#\s*include|\.include|\$include|include|\.INCLUDE|\.inc|\.copy|GET)\s*[<"\'(]?\s*([^>"\')\s;]+)', re.I)
EQU_RES = [
    re.compile(r'^\s*#\s*define\s+(\w+)(?:\s+(.*))?$'),
    re.compile(r'^([A-Za-z_?][\w?.]*)\s*:?\s+(?:\.?equ|\.?set|\.assign|=)\s+(.+)$', re.I),
    re.compile(r'^\s*\.(?:equ|set|equiv|eqv|def|define)\s+([\w.]+)\s*[=,]?\s*(.+)$', re.I),
    re.compile(r'^\s+([A-Za-z_]\w*)\s*=\s*([^=].*)$'),
]
SEC_RE = re.compile(r'^\s*(?:\.(section|segment|area|psect|cseg|dseg|eseg|xseg|bseg|text|data|bss|rodata|sect)\b\s*(?:/\s*\w+\s*)?([^;\s,]*)'
                    r'|(RSEG|SECTION|AREA|CSEG|DSEG|XSEG|ISEG|BSEG|ASEG|CODE|UDATA|UDATA_SHR|UDATA_ACS|IDATA|PSECT|SEGMENT)\b\s*([^;\s,]*))', re.I)
ORG_RE = re.compile(r'^\s*(?:[A-Za-z_]\w*\s+)?\.?org\s+([^;\s]+)', re.I)
MAC_START = [
    re.compile(r'^\s*\.macro\s+([\w.$]+)\s*,?\s*(.*)$', re.I),
    re.compile(r'^([A-Za-z_?][\w?.]*)\s*:?\s+MACRO\b\s*(.*)$', re.I),
    re.compile(r'^\s+MACRO\s*$', re.I),           # ARM armasm: name on next line
    re.compile(r'^\s*%macro\s+(\w+)\s*(.*)$', re.I),
]
MAC_END = re.compile(r'^\s*(\.endm|\.endmacro|ENDM|MEND|%endmacro)\b', re.I)
EXT_RE = re.compile(r'^\s*(?:\.extern|\.extrn|EXTERN|EXTRN|IMPORT|\.import|\.ref|XREF)\s+(.+)$', re.I)
GLOB_RE = re.compile(r'^\s*(?:\.global|\.globl|\.globa|\.public|GLOBAL|PUBLIC|EXPORT|XDEF|\.def|\.export|\.GLB)\s+([^;/]+)', re.I)
FUNCTYPE_RE = re.compile(r'^\s*(?:\.type\s+([\w.$]+)\s*,\s*[%@#]?(?:function|STT_FUNC)|\.func\s+([\w.$]+)|\.ent\s+([\w.$]+)|\.cc_top\s+([\w.$]+)\.function|\.thumb_func\b|\.dbfunc\s+\w\s+\w+\s+([\w.$]+))', re.I)
PROC_RE = re.compile(r'^\s*([A-Za-z_?][\w?.]*)\s+PROC\b', re.I)
PROCESSOR_RES = [
    (re.compile(r'\bLIST\s+.*?P\s*=\s*([\w]+)', re.I), lambda m: 'PIC' + m.group(1).upper() if not m.group(1).upper().startswith('PIC') else m.group(1).upper()),
    (re.compile(r'^\s*PROCESSOR\s+(\w+)', re.I | re.M), lambda m: 'PIC' + m.group(1).upper().lstrip('PIC')),
    (re.compile(r'#include\s*[<"](?:.*[/\\])?p(1[0-9][a-z]*\d+\w*)\.inc', re.I), lambda m: 'PIC' + m.group(1).upper()),
    (re.compile(r'\.include\s*"(?:.*[/\\])?m(\d+\w*?)def\.inc"', re.I), lambda m: 'ATmega' + m.group(1).upper()),
    (re.compile(r'\.include\s*"(?:.*[/\\])?(tn|can|usb|pwm)(\d+\w*?)def\.inc"', re.I), lambda m: {'tn': 'ATtiny', 'can': 'AT90CAN', 'usb': 'AT90USB', 'pwm': 'AT90PWM'}[m.group(1).lower()] + m.group(2).upper()),
    (re.compile(r'\.device\s+(\w+)', re.I), lambda m: m.group(1)),
    (re.compile(r'[<"]iom(\d+\w*?)v?\.h[>"]', re.I), lambda m: 'ATmega' + m.group(1).upper()),
    (re.compile(r'[<"]io(can\d+)v?\.h[>"]', re.I), lambda m: 'AT90' + m.group(1).upper()),
    (re.compile(r'def(21\d\d\d\w?)\.h', re.I), lambda m: 'ADSP-' + m.group(1).upper()),
    (re.compile(r'def(BF\d+\w*)\.h', re.I), lambda m: 'ADSP-' + m.group(1).upper()),
    (re.compile(r'\b(ADSP-21\d+\w*)', re.I), lambda m: m.group(1).upper()),
    (re.compile(r'[<"](?:.*[/\\])?(?:reg|at)?(89c\w+|80c\d+\w*|c8051\w+)\.(?:inc|h)[>"]', re.I), lambda m: m.group(1).upper()),
    (re.compile(r'\b(AT91SAM\w+|STM32\w+|STR7\d+\w*|LPC\d{4}\w*|AT32UC3\w+|MSP430\w+)', re.I), lambda m: re.sub(r'_(INC|H|DEF|ASM)$', '', m.group(1).upper())),
]


def _detect_dialect(text):
    sample = text[:300000]
    best, bscore = None, 0
    for key, name, rx, w in DIALECTS:
        n = len(re.findall(rx, sample, re.I | re.M))
        score = n * w
        if key == 'imagecraft' and n:
            return key, name
        if key == 'xmos' and n >= 2:
            return key, name
        if score > bscore:
            best, bscore = (key, name), score
    if best and bscore >= 2:
        k = best[0]
        if k == 'arm' and re.search(r'\.(global|globl|section|text)\b', sample):
            return k, 'ARM assembly (GNU as)'
        if k == 'arm' and re.search(r'^\s*(RSEG|SECTION|PUBLIC|EXTERN)\b', sample, re.M):
            return k, 'ARM assembly (IAR)'
        if k == 'arm' and re.search(r'^\s*AREA\b', sample, re.M):
            return k, 'ARM assembly (Keil/armasm)'
        if k == 'avr' and re.search(r'^\s*\.(area|module)\b', sample, re.M):
            return k, 'Atmel AVR assembly (ImageCraft assembler)'
        return best
    if re.search(r'^\s*\.(globl|global|section|text|data)\b', sample, re.M):
        return 'gnu', 'GNU as assembly'
    return 'generic', 'assembly source'


def _processor(text):
    sample = re.sub(r'(?m)^\s*;.*$', '', text[:200000])
    for rx, fn in PROCESSOR_RES:
        m = rx.search(sample)
        if m:
            try:
                return fn(m)
            except Exception:
                continue
    return ''


class Line:
    __slots__ = ('no', 'raw', 'code', 'comment', 'hc')

    def __init__(self, no, raw, code, comment, hc=False):
        self.no, self.raw, self.code, self.comment = no, raw, code, comment
        self.hc = hc or bool(comment)


def _split_lines(text, dialect):
    """Yield Line objects with code/comment separated for the dialect."""
    semicolon_is_comment = dialect not in ('sharc', 'blackfin', 'adsp21xx')
    at_comment = dialect == 'arm'
    hash_comment = dialect in ('xmos', 'gnu', 'arm', 'm68k', 'renesas')
    braces = dialect == 'adsp21xx'
    out = []
    in_block = False
    in_brace = False
    SPECIAL = ';/"\'{!@#'
    for no, raw in enumerate(text.split('\n'), 1):
        s = raw
        code, comment = [], []
        i, n = 0, len(s)
        if in_block:
            j = s.find('*/')
            if j < 0:
                out.append(Line(no, raw, '', s.strip(' \t*'), True)); continue
            comment.append(s[:j].strip(' \t*')); i = j + 2; in_block = False
        if in_brace:
            j = s.find('}')
            if j < 0:
                out.append(Line(no, raw, '', s.strip(), True)); continue
            comment.append(s[:j].strip()); i = j + 1; in_brace = False
        q = None
        if i == 0 and not any(ch in s for ch in SPECIAL):
            out.append(Line(no, raw, s.rstrip(), '')); continue
        if i == 0 and semicolon_is_comment and '"' not in s and "'" not in s and '/' not in s and '{' not in s and '#' not in s and '@' not in s and '!' not in s:
            j = s.find(';')
            out.append(Line(no, raw, s[:j].rstrip(), s[j + 1:].strip(), True)); continue
        while i < n:
            c = s[i]
            if q:
                code.append(c)
                if c == q:
                    q = None
                i += 1; continue
            if c in '"' or (c == "'" and dialect not in ('pic',) and i + 2 < n and s[i + 2] == "'"):
                q = c; code.append(c); i += 1; continue
            if c == ';' and semicolon_is_comment:
                comment.append(s[i + 1:].strip()); break
            if c == '/' and s.startswith('//', i):
                comment.append(s[i + 2:].strip()); break
            if c == '/' and s.startswith('/*', i):
                j = s.find('*/', i + 2)
                if j < 0:
                    comment.append(s[i + 2:].strip(' \t*')); in_block = True; break
                comment.append(s[i + 2:j].strip(' \t*')); i = j + 2; continue
            if c == '{' and braces:
                j = s.find('}', i + 1)
                if j < 0:
                    comment.append(s[i + 1:].strip()); in_brace = True; break
                comment.append(s[i + 1:j].strip()); i = j + 1; continue
            if c == '!' and dialect == 'sharc' and (i == 0 or s[i - 1] in ' \t;') and not s.startswith('!=', i):
                comment.append(s[i + 1:].strip()); break
            if c == '@' and at_comment and (i == 0 or s[i - 1] in ' \t'):
                comment.append(s[i + 1:].strip()); break
            if c == '#' and hash_comment and not ''.join(code).strip() and not re.match(r'#\s*(include|define|if|ifdef|ifndef|else|elif|endif|undef|pragma|error|line)\b', s[i:]) and (i + 1 >= n or not s[i + 1].isdigit()):
                comment.append(s[i + 1:].strip()); break
            code.append(c); i += 1
        out.append(Line(no, raw, ''.join(code).rstrip(), ' '.join(x for x in comment if x), bool(comment) or in_block or in_brace))
    return out


COLON_LABEL = re.compile(r'^\s*([A-Za-z_.$?@][\w.$?@]*)\s*(::?)(?!=)')
COL0_LABEL = re.compile(r'^([A-Za-z_?][\w?.]*)(?:\s*:)?(?=\s|$)')


def _parse_label(code, col0_mode):
    """Return (label, is_double_colon, rest_of_line)."""
    m = COLON_LABEL.match(code)
    if m:
        rest = code[m.end():]
        name = m.group(1)
        if name.lower() in ('case', 'default', 'if') or rest.startswith(':'):
            return None, False, code
        return name, m.group(2) == '::', rest
    if col0_mode and code and not code[0].isspace():
        m = COL0_LABEL.match(code)
        if m:
            name = m.group(1)
            rest = code[m.end():]
            nxt = rest.split(None, 1)[0].lower() if rest.strip() else ''
            if name.lower() in DIRECTIVE_WORDS or name.lower().lstrip('.') in DIRECTIVE_WORDS:
                return None, False, code
            if nxt in ('equ', 'set', 'macro', 'res', '=', 'db', 'dw', 'dt', 'de', 'ds', 'data', 'cblock', 'dcd', 'dcb', 'dcw',
                       'byte', 'word', '.equ', '.set', 'segment', 'proc', 'endp', 'ends', 'udata', 'code', 'idata', 'udata_shr',
                       'variable', 'constant', 'fill', 'space', 'rmb', 'fcb', 'fdb', 'dc.b', 'dc.w', 'dc.l', 'ds.b') or rest.lstrip().startswith('='):
                return None, False, code
            return name, False, rest
    return None, False, code


def _doc_before(lines, idx, maxlines=30):
    """Comment block immediately preceding lines[idx] (skipping directives/blank lines between)."""
    j = idx - 1
    blanks = 0
    while j >= 0:
        L = lines[j]
        if L.code.strip() and SKIP_BACK.match(L.code):
            j -= 1; continue
        if not L.code.strip() and not L.hc:
            blanks += 1
            if blanks > 1:
                return ''
            j -= 1; continue
        break
    buf = []
    while j >= 0 and len(buf) < maxlines:
        L = lines[j]
        if L.code.strip():
            if SKIP_BACK.match(L.code):
                j -= 1; continue
            break
        if not L.hc:
            if not L.raw.strip() and buf:
                # allow a single blank line inside a banner
                if j > 0 and lines[j - 1].comment and not lines[j - 1].code.strip():
                    j -= 1; continue
            break
        buf.append(L.comment if L.comment else '')
        j -= 1
    buf.reverse()
    return _clean_doc(buf)


def _clean_doc(buf):
    out = []
    for c in buf:
        c = c.strip()
        c2 = c.strip('*-=#;~+_/!<> \t')
        if not c2:
            continue
        out.append(c2 if len(c2) < len(c) and re.match(r'^[*\-=#;~+_/!]{3,}', c) else c)
    return '\n'.join(out).strip()


def _prose(p):
    """True if a comment block reads like prose (not commented-out code / tables)."""
    ls = [l for l in p.split('\n') if l.strip()]
    if not ls:
        return False
    codey = sum(1 for l in ls if re.match(r'^\s*(#\s*(define|include|if|endif)|[\w\[\]]+\s*=|\w+\s*\(.*\)\s*;|[{}]|(movlw|movwf|bsf|bcf|ldi|call|goto)\b)', l, re.I) or l.rstrip().endswith(';'))
    words = re.findall(r'[A-Za-z]{3,}', p)
    alpha = sum(c.isalpha() or c == ' ' for c in p) / max(1, len(p))
    return codey <= len(ls) * 0.3 and len(words) >= 4 and alpha > 0.6 and not re.search(r'copyright|warranty|licen[cs]e|all rights|https?://|www\.', p, re.I)


def _proto_params(proto, doc):
    m = re.search(r'\((.*)\)', proto)
    if not m or m.group(1).strip() in ('', 'void'):
        return []
    out = []
    for p in m.group(1).split(','):
        pm = re.match(r'^(.*?)([A-Za-z_]\w*)\s*(\[.*\])?$', p.strip())
        if pm:
            out.append([pm.group(2), (pm.group(1).strip() or '?') + (pm.group(3) or ''), ''])
    dl = doc.split('\n')
    # register row printed under the prototype (SHARC C-callable convention)
    for k, ln in enumerate(dl):
        if proto.split('(')[0].split()[-1] in ln and k + 1 < len(dl):
            regs = re.findall(r"\b(R\d+|r\d+|stack\[\d+\]|W\d+|I\d+)(?!\w)", dl[k + 1])
            if regs and len(dl[k + 1].split()) == len(regs):
                for p, r in zip(out, regs):
                    p[2] = f'in {r}'
            break
    for ln in dl:
        mm = re.match(r'^\s*(\w+)\s*:\s*(.+)$', ln)
        if mm:
            for p in out:
                if p[0] == mm.group(1):
                    p[2] = (p[2] + ' — ' if p[2] else '') + mm.group(2).strip()
    return [tuple(p) for p in out]


def _is_zero(a):
    try:
        return int(re.sub(r'^(0x|\$)|[hH]$', '', str(a)) or '0', 16) == 0
    except ValueError:
        return False


def _proto_from_doc(doc, name):
    base = name.lstrip('_')
    for ln in doc.split('\n'):
        m = re.search(r'([A-Za-z_][\w\s\*]*?\b_?' + re.escape(base) + r'\s*\([^)]*\))', ln)
        if m and re.search(r'\b(void|int|char|short|long|float|double|unsigned|signed|ushort|uint\w*|bool|\w+_t)\b', m.group(1)):
            return m.group(1).strip()
    return ''


def _asm(path, text, notes, listing_meta=None):
    dialect, dname = _detect_dialect(text)
    if dialect == 'imagecraft':
        return _imagecraft(path, text, notes, listing_meta)
    lines = _split_lines(text, dialect)
    n_colon = sum(1 for L in lines if COLON_LABEL.match(L.code))
    col0_cands = sum(1 for L in lines if L.code and not L.code[0].isspace() and COL0_LABEL.match(L.code))
    col0_mode = dialect in ('pic', '8051') or (col0_cands > 2 * n_colon and dialect not in ('sharc', 'blackfin', 'gnu', 'xmos'))
    if dialect == 'arm' and re.search(r'^\s*(RSEG|SECTION|AREA|PUBLIC|EXPORT)\b', text[:200000], re.M):
        col0_mode = True

    labels = []          # (idx, name, dbl)
    globals_, functyped, call_targets, jump_targets = set(), set(), collections.Counter(), set()
    macros = []
    includes, equs, secs, orgs, externs, data_vars = [], [], collections.OrderedDict(), [], [], []
    vec_targets = []
    xmos_calls = collections.defaultdict(list)
    pending_type = None
    in_macro = None
    org_recent = None
    instr_count = 0
    proc_names = set()
    arm_macro_next = False
    cfg = []

    for idx, L in enumerate(lines):
        code = L.code
        cs = code.strip()
        if not cs:
            continue
        low = cs.lower()
        # ---- macros
        if in_macro is not None:
            if MAC_END.match(code):
                in_macro['end'] = L.no
                in_macro = None
            continue
        if arm_macro_next:
            arm_macro_next = False
            nm = cs.split()[0] if cs.split() else '?'
            nm = nm.lstrip('$')
            if len(cs.split()) > 1 and cs.split()[0].startswith('$'):
                nm = cs.split()[1]
            in_macro = {'name': nm, 'line': L.no, 'sig': cs, 'idx': idx}
            macros.append(in_macro); continue
        mm = None
        for k, rx in enumerate(MAC_START):
            mm = rx.match(code)
            if mm:
                if k == 2:
                    arm_macro_next = True
                    break
                in_macro = {'name': mm.group(1), 'line': L.no, 'sig': cs, 'idx': idx}
                macros.append(in_macro)
                break
        if mm:
            continue
        # ---- outline directives
        m = INC_RE.match(code)
        if m and not re.match(r'^\s*include\w', code, re.I):
            includes.append(m.group(1)); continue
        m = GLOB_RE.match(code)
        if m:
            for g in re.split(r'[,\s]+', m.group(1).strip().rstrip(';')):
                if g and re.match(r'^[A-Za-z_.$?@][\w.$?@]*$', g):
                    globals_.add(g)
            continue
        m = FUNCTYPE_RE.match(code)
        if m:
            nm = next((g for g in m.groups() if g), None)
            if nm:
                functyped.add(nm)
            elif '.thumb_func' in low:
                pending_type = True
            if not low.startswith('.cc_top'):
                continue
        m = re.match(r'^\s*\.call\s+([\w.$]+)\s*,\s*([\w.$]+)', code)
        if m:
            xmos_calls[m.group(1)].append(m.group(2)); continue
        m = EXT_RE.match(code)
        if m:
            externs.extend(x for x in re.split(r'[,\s]+', m.group(1).strip().rstrip(';')) if x and re.match(r'^[\w.$?@]+$', x) and x.lower() not in ('code', 'data'))
            continue
        m = PROC_RE.match(code)
        if m:
            proc_names.add(m.group(1))
        if re.match(r'^\s*__CONFIG\b|^\s*CONFIG\s+\w+\s*=', code, re.I):
            cfg.append(cs)
        m = ORG_RE.match(code)
        if m:
            orgs.append([L.no, m.group(1), None])
            org_recent = [0, orgs[-1]]
            continue
        m = SEC_RE.match(code)
        if m:
            sec = (m.group(1) or m.group(3) or '').lower()
            nm = m.group(2) if m.group(1) else m.group(4)
            key = f'{sec} {nm}'.strip() if nm else sec
            if not re.match(r'^\.?(text|data|bss)$', key) or True:
                secs[key] = secs.get(key, 0) + 1
            if sec in ('section', 'segment', 'area', 'psect', 'text', 'data', 'bss', 'rodata', 'cseg', 'dseg', 'rseg', 'code', 'udata', 'idata') and not m.group(1) is None or m.group(3):
                pass
            if not COLON_LABEL.match(code):
                continue
        # ---- equates / variables
        hit = False
        for rx in (EQU_RES if dialect not in ('sharc', 'blackfin', 'adsp21xx', 'm68k', 'renesas', 'arm') else EQU_RES[:3]):
            m = rx.match(code)
            if m and m.group(2) and m.group(2).rstrip().endswith(';') and rx is EQU_RES[3]:
                m = None
            if m and not CALL_RE.search(code):
                if len(equs) < 400:
                    equs.append((m.group(1), (m.group(2) or '').strip()[:60], L.comment[:60]))
                hit = True
                break
        if hit:
            continue
        m = re.match(r'^([A-Za-z_]\w*)\s*:?\s+(RES|DS|DS\.[BWL]|RMB|\.blkb|\.blkw|\.space|DB|DW|DCB|DCD|\.byte|\.word|\.long|\.var)\b\s*(.*)$', code, re.I)
        if m and col0_mode:
            data_vars.append((m.group(1), m.group(2), m.group(3)[:40], L.comment[:50]))
            continue
        m = re.match(r'^\s*\.var\s*(?:=\s*)?([A-Za-z_]\w*)', code, re.I)
        if m:
            data_vars.append((m.group(1), '.var', '', L.comment[:50])); continue
        # ---- labels
        name, dbl, rest = _parse_label(code, col0_mode)
        if name:
            labels.append((idx, name, dbl))
            if dbl:
                globals_.add(name)
            if pending_type:
                functyped.add(name); pending_type = None
            if org_recent is not None and org_recent[1][2] is None:
                org_recent[1][2] = name
            code = rest
            cs = code.strip()
            low = cs.lower()
            if not cs:
                continue
        # ---- instructions
        instr_count += 1
        for m in CALL_RE.finditer(code):
            t = m.group(2)
            if not REGS.match(t):
                call_targets[t] += 1
        m = JUMP_RE.search(code)
        if m and not REGS.match(m.group(2)):
            jump_targets.add(m.group(2))
            if org_recent is not None and org_recent[0] < 8:
                vec_targets.append((org_recent[1][1] if org_recent[0] == 0 else f'{org_recent[1][1]} +{org_recent[0]}', m.group(2)))
                if org_recent[1][2] is None:
                    org_recent[1][2] = f'→ {m.group(2)}'
        m = re.match(r'^\s*(?:\.word|\.long|\.4byte|DCD|\.int)\s+([A-Za-z_]\w*)\s*$', code, re.I)
        if m and labels and VEC_NAME.search(labels[-1][1]):
            vec_targets.append((labels[-1][1], m.group(1)))
        if org_recent is not None:
            org_recent[0] += 1
            if org_recent[0] >= 8:
                org_recent = None

    # ---- decide routine starts
    label_names = [n for _, n, _ in labels]
    nonlocal_labels = [(i, n, d) for i, n, d in labels if not LOCAL_RE.match(n)]
    vec_set = {t for a, t in vec_targets if not _is_zero(a)}
    reset_targets = {t for a, t in vec_targets if _is_zero(a)}
    strong = set(globals_) | functyped | set(call_targets) | vec_set | reset_targets | proc_names | set(xmos_calls)
    strong |= {n for _, n, _ in nonlocal_labels if ENTRY_NAME.match(n)}
    starts = [(i, n) for i, n, _ in labels if n in strong]
    seen = set(n for _, n in starts)

    # labels with their own comment banner whose block returns (helper routines reached by goto)
    def region_has_ret(i0, i1):
        for L in lines[i0:i1]:
            if L.code and RET_RE.search(L.code):
                return True
        return False

    lab_idx = [i for i, _, _ in labels]
    weak = []
    for k, (i, n, d) in enumerate(labels):
        if n in seen or LOCAL_RE.match(n):
            continue
        nxt = lab_idx[k + 1] if k + 1 < len(lab_idx) else len(lines)
        doc = _doc_before(lines, i, 6)
        if doc and len(doc) > 8 and region_has_ret(i, nxt):
            weak.append((i, n))
    if not starts:
        # nothing called/declared: every non-local label that ends in a return
        for k, (i, n, d) in enumerate(labels):
            if LOCAL_RE.match(n):
                continue
            nxt = lab_idx[k + 1] if k + 1 < len(lab_idx) else len(lines)
            if region_has_ret(i, nxt):
                weak.append((i, n))
    if not starts and not weak and len(nonlocal_labels) <= 300:
        weak = [(i, n) for i, n, _ in nonlocal_labels]
    allstarts = sorted({(i, n) for i, n in starts + weak})
    if len(allstarts) > MAX_FUNCS:
        notes.append(f'{len(allstarts):,} routines found; first {MAX_FUNCS:,} listed.')
        allstarts = allstarts[:MAX_FUNCS]

    # routine boundaries: next start, or a section change/END
    functions = []
    macro_idx = [(m['idx'], m.get('end')) for m in macros]
    for k, (i, n) in enumerate(allstarts):
        end = allstarts[k + 1][0] if k + 1 < len(allstarts) else len(lines)
        calls, rets, irets, inner = [], 0, 0, []
        last_code = ''
        for L in lines[i:end]:
            c = L.code
            if not c.strip():
                continue
            ln, _, rest = _parse_label(c, col0_mode)
            if ln and ln != n and len(inner) < 40:
                inner.append(ln)
            if ln:
                c = rest
            for m in CALL_RE.finditer(c):
                t = m.group(2)
                if not REGS.match(t) and t not in calls:
                    calls.append(t)
            if RET_RE.search(c):
                rets += 1
                if IRET_RE.search(c):
                    irets += 1
            if c.strip():
                last_code = c.strip()
        for t in xmos_calls.get(n, []):
            if t not in calls:
                calls.append(t)
        doc = _doc_before(lines, i)
        endline = lines[min(end, len(lines)) - 1].no
        kind = 'routine'
        retre = RET_RE.search(last_code) if last_code else None
        if ENTRY_NAME.match(n) or n in reset_targets:
            kind = 'entry point'
        elif n in vec_set or VEC_NAME.search(n) or (irets and irets * 2 >= rets):
            kind = 'interrupt handler'
        elif dialect in ('xmos',) or n in functyped:
            kind = 'function'
        if n in globals_ and kind == 'routine':
            kind = 'global routine'
        proto = _proto_from_doc(doc, n)
        sig = lines[i].raw.strip().expandtabs(8)
        sig = (f'{proto}   // per header comment\n' if proto else '') + sig + f'      ; lines {lines[i].no}–{endline}'
        if inner:
            sig += '\n; internal labels: ' + ', '.join(inner[:20]) + (' …' if len(inner) > 20 else '')
        ret = ''
        if rets:
            ret = f'{rets} exit point{"s" if rets != 1 else ""}' + (f' ({irets} interrupt return{"s" if irets != 1 else ""})' if irets else '')
        elif last_code and not retre:
            ret = 'no return instruction (falls through, loops or jumps away)'
        f = {'name': n, 'kind': kind, 'line': lines[i].no, 'signature': sig, 'doc': doc, 'returns': ret, 'calls': calls}
        if proto:
            f['params'] = _proto_params(proto, doc)
        functions.append(f)
    for L in lines:
        mm = re.match(r'^\s*#\s*define\s+(\w+)(\([^)]*\))?\s+(.*;.*)$', L.raw)
        if mm and dialect in ('sharc', 'blackfin', 'adsp21xx', 'generic', 'gnu', 'arm') and len(functions) < MAX_FUNCS:
            body = mm.group(3).strip()
            functions.append({'name': mm.group(1), 'kind': 'macro (#define)', 'line': L.no,
                              'signature': L.raw.strip().replace(';', ';\n    ').rstrip(), 'doc': L.comment if L.code.strip() else '',
                              'params': [(x.strip(), 'macro argument', '') for x in (mm.group(2) or '').strip('()').split(',') if x.strip()]})
    for m in macros:
        doc = _doc_before(lines, m['idx'])
        params = []
        mm = re.match(r'^\s*(?:\.macro\s+[\w.$]+|[\w?.]+\s*:?\s+MACRO|%macro\s+\w+)\s*,?\s*(.*)$', m['sig'], re.I)
        if mm and mm.group(1).strip():
            params = [(p.strip().split('=')[0].strip(), 'macro argument', '') for p in re.split(r'[,\s]+', mm.group(1).strip()) if p.strip()]
        functions.append({'name': m['name'], 'kind': 'macro', 'line': m['line'],
                          'signature': m['sig'] + (f"      ; lines {m['line']}–{m['end']}" if m.get('end') else ''),
                          'doc': doc, 'params': params[:20]})
    functions.sort(key=lambda f: f.get('line') or 0)

    # ---- outline
    outline = []
    if includes:
        outline.append({'heading': f'Includes ({len(includes)})'})
        outline += [f'`{x}`' for x in dict.fromkeys(includes)]
    if orgs:
        outline.append({'heading': f'ORG addresses ({len(orgs)})'})
        outline += [f'`ORG {a}` (line {no})' + (f' → `{lab}`' if lab and not lab.startswith('→') else (f' {lab}' if lab else '')) for no, a, lab in orgs[:100]]
    if vec_targets:
        outline.append({'heading': 'Vector table / reset & interrupt entries'})
        outline += [f'`{a}` → `{t}`' for a, t in vec_targets[:100]]
    if secs:
        outline.append({'heading': f'Sections / segments ({len(secs)})'})
        outline += [f'`{k}`' + (f' ×{v}' if v > 1 else '') for k, v in list(secs.items())[:80]]
    if globals_:
        g = sorted(globals_)
        outline.append({'heading': f'Exported / global symbols ({len(g)})'})
        outline.append(', '.join(f'`{x}`' for x in g[:300]) + (' …' if len(g) > 300 else ''))
    if externs:
        e = list(dict.fromkeys(externs))
        outline.append({'heading': f'External symbols ({len(e)})'})
        outline.append(', '.join(f'`{x}`' for x in e[:300]) + (' …' if len(e) > 300 else ''))
    if cfg:
        outline.append({'heading': 'Configuration words'})
        outline += [f'`{c[:120]}`' for c in cfg[:20]]
    if equs:
        outline.append({'heading': f'Equates / defines ({len(equs)}{"+" if len(equs) >= 400 else ""}, first 80)'})
        for nm, v, cm in equs[:80]:
            outline.append(f'`{nm}` = `{v.replace("`", "")}`' + (f' — {cm}' if cm else '') if v else f'`{nm}`' + (f' — {cm}' if cm else ''))
    if data_vars:
        outline.append({'heading': f'Data / RAM variables ({len(data_vars)}, first 80)'})
        for nm, d, v, cm in data_vars[:80]:
            outline.append(f'`{nm}`' + (f' [{v.strip()}]' if v.strip() else '') + (f' — {cm}' if cm else ''))

    # ---- paragraphs: the prose (comment blocks) in reading order
    pars, buf = [], []
    for L in lines:
        if L.comment and not L.code.strip():
            c = L.comment.strip()
            c2 = c.strip('*-=#;~+_/!<> \t')
            if c2:
                buf.append(c2 if re.match(r'^[*\-=#;~+_/!]{3,}', c) else c)
            continue
        if buf:
            pars.append('\n'.join(buf)); buf = []
    if buf:
        pars.append('\n'.join(buf))
    # drop pure commented-out code lines? keep: they are part of the file's text
    pars = _cap_pars(pars, notes)

    proc = _processor(text)
    meta = [('Assembler dialect', dname)]
    if proc:
        meta.append(('Target processor', proc))
    meta.append(('Lines', f'{len(lines):,}'))
    meta.append(('Instructions (approx.)', f'{instr_count:,}'))
    nr = sum(1 for f in functions if not f['kind'].startswith('macro'))
    mnames = [f['name'] for f in functions if f['kind'].startswith('macro')]
    meta.append(('Routines', nr))
    if mnames:
        meta.append(('Macros', len(mnames)))
    if listing_meta:
        meta = listing_meta + meta
    m = re.search(r'^\s*\.file\s+(?:\d+\s+)?"([^"]+)"', text[:5000], re.M)
    if m:
        meta.append(('Compiled from', f'`{m.group(1)}`'))

    # summary: header comment + routine list
    header = ''
    for p in pars[:6]:
        if len(p) > 25 and _prose(p):
            header = ' '.join(x.strip() for x in p.split('\n')[:8]); break
    rnames = [f['name'] for f in functions if not f['kind'].startswith('macro')]
    summ = f'{dname}' + (f' for {proc}' if proc else '')
    if header:
        summ += f': {header[:420].rstrip()}' + ('…' if len(header) > 420 else '')
    summ = summ.rstrip('.') + '.'
    if rnames:
        summ += f' Defines {len(rnames)} routine{"s" if len(rnames) != 1 else ""}: ' + ', '.join(rnames[:20]) + (' …' if len(rnames) > 20 else '') + '.'
    if mnames:
        summ += f' {len(mnames)} macro{"s" if len(mnames) != 1 else ""}: ' + ', '.join(mnames[:12]) + (' …' if len(mnames) > 12 else '') + '.'
    kws = ([proc] if proc else []) + [x for x in rnames[:6]] + [x for x in includes[:3]]
    return {'kind': 'source', 'type': dname, 'summary': summ, 'keywords': kws, 'meta': meta,
            'functions': functions, 'outline': outline, 'paragraphs': pars, 'code_lang': 'asm', 'notes': notes}


# ---------------------------------------------------------------- ImageCraft
ICC_RT = re.compile(r'^(push_|pop_)(x?gset|arg)\w*$|^(push|pop)_\w*gset', re.I)


def _imagecraft(path, text, notes, listing_meta=None):
    lines = text.split('\n')
    module = ''
    m = re.search(r'^\s*\.module\s+(\S+)', text[:5000], re.M)
    if m:
        module = m.group(1)
    csrc = []            # recovered C source: (asm line idx, text)
    funcs = []
    cur = None
    globals_data = []
    areas = collections.Counter()
    instr = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            continue
        if s.startswith(';'):
            body = ln.split(';', 1)[1]
            if cur is not None and cur.get('in_hdr') and re.match(r'^\s+[\w.\[\]]+\s+->\s+\S', body):
                mm = re.match(r'^\s+([\w.\[\]]+)\s+->\s+(.+)$', body)
                cur['regs'].append((mm.group(1), mm.group(2).strip()))
                continue
            if body.startswith(' ') or body.startswith('\t') or body == '':
                csrc.append((i, body[1:] if body.startswith(' ') else body))
            continue
        tok = s.split(None, 1)
        d = tok[0].lower()
        if d == '.dbfunc':
            p = s.split()
            nm = p[2] if len(p) > 2 else '?'
            cur = {'name': nm, 'idx': i, 'line': i + 1, 'scope': p[1] if len(p) > 1 else '', 'tcode': p[4] if len(p) > 4 else '',
                   'regs': [], 'calls': [], 'in_hdr': True, 'csrc_start': len(csrc), 'end': None}
            funcs.append(cur)
            continue
        if d == '.dbend' and cur is not None:
            cur['end'] = i + 1; cur['csrc_end'] = len(csrc); cur = None
            continue
        if d == '.area':
            areas[tok[1].split('(')[0].strip() if len(tok) > 1 else '?'] += 1
            continue
        if d == '.dbsym' and cur is None:
            p = s.split()
            if len(p) >= 3 and p[1] in ('e', 's'):
                globals_data.append((p[2], 'extern' if p[1] == 'e' else 'static', p[-1]))
            continue
        if d.startswith('.') or s.endswith('::') or s.endswith(':'):
            if cur is not None and s.endswith('::'):
                pass
            continue
        instr += 1
        if cur is not None:
            cur['in_hdr'] = False
            mm = re.match(r'^(x?call|rcall|icall)\s+(\S+)', s, re.I)
            if mm:
                t = mm.group(2).lstrip('_')
                if not ICC_RT.match(mm.group(2)) and t not in cur['calls']:
                    cur['calls'].append(t)
    ctext = '\n'.join(t for _, t in csrc)
    clines = [t for _, t in csrc]
    out_funcs = []
    for f in funcs[:MAX_FUNCS]:
        a, b = f['csrc_start'], f.get('csrc_end', len(clines))
        seg = clines[a:b]
        name = f['name']
        sig, doc, sig_at = '', '', None
        for k, t in enumerate(seg):
            if re.search(r'\b' + re.escape(name) + r'\s*\(', t) and not re.match(r'^\s*(//|/\*|\*)', t) and not t.rstrip().endswith(';'):
                sig_at = k; break
        if sig_at is None:
            # signature may have been emitted before .dbfunc (end of previous function region)
            for k in range(a - 1, max(-1, a - 40), -1):
                if re.search(r'\b' + re.escape(name) + r'\s*\(', clines[k]) and not clines[k].rstrip().endswith(';'):
                    seg = clines[k:b]; sig_at = 0; a = k; break
        if sig_at is not None:
            buf = []
            for t in seg[sig_at:sig_at + 6]:
                buf.append(t.strip())
                if '{' in t or ')' in t:
                    break
            sig = ' '.join(buf).split('{')[0].strip()
            # comments directly above
            dl = []
            k = a + sig_at - 1
            while k >= 0 and len(dl) < 15:
                t = clines[k].strip()
                if not t:
                    if dl:
                        break
                    k -= 1; continue
                if re.match(r'^(//|/\*|\*|\*/)', t) or t.endswith('*/'):
                    dl.append(t); k -= 1; continue
                break
            dl.reverse()
            doc = _clean_doc([re.sub(r'^(//+|/\*+|\*+/?|\*/)', '', x).replace('*/', '') for x in dl])
        params = []
        pnames = []
        if sig:
            mm = re.search(r'\((.*)\)', sig)
            if mm and mm.group(1).strip() not in ('', 'void'):
                for p in mm.group(1).split(','):
                    p = p.strip()
                    pm = re.match(r'^(.*?)([A-Za-z_]\w*)\s*(\[.*\])?$', p)
                    if pm:
                        pnames.append(pm.group(2))
                        params.append([pm.group(2), (pm.group(1).strip() or 'int') + (pm.group(3) or ''), ''])
        regs = dict(f['regs'])
        for p in params:
            if p[0] in regs:
                p[2] = f'passed in {regs[p[0]]}'
        loc = [f'{k} → {v}' for k, v in f['regs'] if k not in pnames]
        ret = ''
        if sig:
            pre = sig.split('(')[0]
            pre = re.sub(r'\b' + re.escape(name) + r'\s*$', '', pre).strip()
            pre = re.sub(r'^(static|extern|inline)\s+', '', pre)
            ret = pre if pre else 'int'
        extra = f"// asm lines {f['line']}–{f.get('end') or '?'}, " + ('static' if f['scope'] == 's' else 'external linkage')
        if loc:
            extra += '\n// locals: ' + ', '.join(loc[:12])
        out_funcs.append({'name': name, 'kind': 'static function' if f['scope'] == 's' else 'function', 'line': f['line'],
                          'signature': (sig or f'.dbfunc {f["scope"]} {name}') + '\n' + extra,
                          'doc': doc,
                          'params': [tuple(p) for p in params], 'returns': ret if ret and ret != 'void' else '',
                          'calls': f['calls']})
    if len(funcs) > MAX_FUNCS:
        notes.append(f'{len(funcs):,} functions; first {MAX_FUNCS:,} listed.')
    proc = _processor(ctext) or _processor(text)
    incs = re.findall(r'^\s*#\s*include\s*[<"]([^>"]+)', ctext, re.M)
    outline = []
    if incs:
        outline.append({'heading': 'C includes'}); outline += [f'`{x}`' for x in dict.fromkeys(incs)]
    defs = re.findall(r'^\s*#\s*define\s+(\w+)[ \t]*(.*)$', ctext, re.M)
    if defs:
        outline.append({'heading': f'#defines ({len(defs)}, first 80)'})
        outline += [f'`{a}` = `{b.strip()[:60].replace("`", "")}`' if b.strip() else f'`{a}`' for a, b in defs[:80]]
    if globals_data:
        outline.append({'heading': f'Global / static data ({len(globals_data)})'})
        outline.append(', '.join(f'`{a}` ({b})' for a, b, _ in globals_data[:300]))
    if areas:
        outline.append({'heading': 'Areas'}); outline += [f'`{k}` ×{v}' for k, v in areas.items()]
    pars = _cap_pars(core.split_paragraphs(ctext), notes) if ctext.strip() else []
    if pars:
        notes.append('Full text below is the C source recovered from the compiler\'s embedded source comments.')
    meta = list(listing_meta or [])
    meta += [('Compiler', 'ImageCraft ICCAVR'), ('C module', f'`{module}`' if module else '?')]
    m = re.search(r'^\s*\.dbfile\s+(.+)$', text[:5000], re.M)
    if m:
        meta.append(('Original path', f'`{m.group(1).strip()}`'))
    if proc:
        meta.append(('Target processor', proc))
    meta += [('Functions', len(out_funcs)), ('AVR instructions', f'{instr:,}')]
    hdr = ''
    for t in core.split_paragraphs(ctext)[:8]:
        cl = [re.sub(r'^\s*(//+|/\*+|\*+/?)', '', x).replace('*/', '').strip() for x in t.split('\n') if re.match(r'^\s*(//|/\*|\*)', x)]
        cand = '\n'.join(x for x in cl if x.strip('*-=/ '))
        if len(cand) > 20 and _prose(cand):
            hdr = ' '.join(cand.split('\n')[:8]); break
    what = 'ImageCraft ICCAVR compiler listing' if listing_meta else 'ImageCraft ICCAVR compiler assembly output'
    summ = f'{what} for C module {module or "?"}' + (f' ({proc})' if proc else '')
    if hdr:
        summ += f'. {hdr[:350]}'
    summ = summ.rstrip('.') + '.'
    if out_funcs:
        summ += f' {len(out_funcs)} function{"s" if len(out_funcs) != 1 else ""}: ' + ', '.join(f['name'] for f in out_funcs[:20]) + (' …' if len(out_funcs) > 20 else '') + '.'
    return {'kind': 'source', 'type': what + ' (AVR)', 'summary': summ, 'meta': meta, 'functions': out_funcs,
            'outline': outline, 'paragraphs': pars, 'code_lang': 'c',
            'keywords': [x for x in [module, proc] if x] + [f['name'] for f in out_funcs[:6]], 'notes': notes}


# ====================================================================== listings
def _listing(path, text, notes):
    lines = text.split('\n')
    meta = []
    head = text[:3000]
    m = re.search(r'(MPASM[^\n]*?\d+\.\d+\w*)', head)
    tool = None
    if m:
        tool = m.group(1).split('  ')[0].strip()
    elif re.search(r'^\s+\.module\s', head, re.M):
        tool = 'ImageCraft ICCAVR'
    else:
        m = re.search(r'^(.*\b(Assembler|Compiler|Linker)\b.*\b[Vv]?\d+\.\d+.*)$', head, re.M)
        if m:
            tool = m.group(1).strip()[:100]
    if tool:
        meta.append(('Listing tool', tool))
    src = []
    # MPASM style:  LOC  OBJECT CODE  LINE SOURCE TEXT
    mp = re.compile(r'^(?:[0-9A-F]{4}\s+)?(?:[0-9A-F]{2,4}\s+){0,4}\s*(\d{5})\s?(.*)$')
    if tool and 'MPASM' in tool:
        for ln in lines:
            mm = mp.match(ln)
            if mm:
                src.append(mm.group(2))
    else:
        # fixed source column: most common indent among lines whose prefix is blank
        cols = collections.Counter()
        pre = re.compile(r'^(\s*(?:[0-9A-Fa-f]{2,8}[:+]?\s+){0,6})(?=\S)')
        for ln in lines[:5000]:
            m = pre.match(ln)
            if m and len(m.group(1)) >= 8:
                cols[len(m.group(1))] += 1
        col = 0
        if cols:
            top = max(cols.values())
            col = min(k for k, v in cols.items() if v >= max(3, top * 0.1))
        prefix_ok = re.compile(r'^[\s0-9A-Fa-f:+.\-]*$')
        for ln in lines:
            if col and len(ln) >= col and prefix_ok.match(ln[:col]):
                src.append(ln[col:])
            elif col and len(ln) < col and prefix_ok.match(ln):
                src.append('')
            elif not col:
                src.append(ln)
            else:
                src.append('')   # page header / error line: keep line numbering aligned
    stext = '\n'.join(src)
    if not stext.strip():
        r = _generic(path, text, notes=notes)
        r['type'] = 'assembler/compiler listing'
        return r
    notes.append('Address/object-code columns removed; source column only.')
    r = _asm(path, stext, notes, listing_meta=meta)
    if r.get('type') and 'listing' not in r['type'].lower():
        r['type'] = r['type'] + ' — listing'
    errs = len(re.findall(r'^\s*(Error|ERROR)\b', text, re.M))
    warns = len(re.findall(r'^\s*(Warning|WARNING)\b', text, re.M))
    if errs or warns:
        r.setdefault('meta', []).append(('Errors / warnings in listing', f'{errs} / {warns}'))
    return r


# ====================================================================== firmware images
def _firmware(path, ext):
    with open(path, 'rb') as f:
        data = f.read(64_000_000)
    try:
        text = data.decode('ascii', 'replace')
    except Exception:
        text = data.decode('latin-1')
    first = next((l.strip() for l in text.split('\n', 20)[:20] if l.strip()), '')
    if first.startswith(':'):
        return _ihex(path, text)
    if re.match(r'^S[0-9]', first):
        return _srec(path, text)
    if core.looks_binary(path):
        return _binary(path, 'binary firmware image')
    return _generic(path, text.replace('\r', ''), typ='text file (not Intel HEX)')


def _ranges(chunks):
    """chunks: list of (addr, length). Merge into contiguous ranges."""
    if not chunks:
        return []
    chunks.sort()
    out = [list(chunks[0])]
    for a, n in chunks[1:]:
        s, ln = out[-1]
        if a <= s + ln:
            out[-1][1] = max(ln, a + n - s)
        else:
            out.append([a, n])
    return out


def _fmt_ranges(rs, width=4, unit='bytes'):
    w = max(width, max((len(f'{a + n - 1:X}') for a, n in rs), default=4))
    return [f'0x{a:0{w}X}–0x{a + n - 1:0{w}X} ({n:,} {unit})' for a, n in rs]


def _ihex(path, text):
    base = 0
    chunks = []
    total = 0
    bad_ck = bad_fmt = 0
    eof = False
    entry = None
    types = collections.Counter()
    reclens = collections.Counter()
    addrs = []
    blob = bytearray()
    nrec = 0
    after_eof = 0
    first_bad = []
    for no, ln in enumerate(text.split('\n'), 1):
        ln = ln.strip()
        if not ln:
            continue
        if eof:
            after_eof += 1
            continue
        if not ln.startswith(':') or len(ln) < 11:
            bad_fmt += 1
            if len(first_bad) < 5:
                first_bad.append(f'line {no}: malformed record')
            continue
        try:
            b = bytes.fromhex(ln[1:])
        except ValueError:
            bad_fmt += 1
            if len(first_bad) < 5:
                first_bad.append(f'line {no}: non-hex characters')
            continue
        nrec += 1
        n, addr, typ = b[0], (b[1] << 8) | b[2], b[3]
        if len(b) != n + 5:
            bad_fmt += 1
            if len(first_bad) < 5:
                first_bad.append(f'line {no}: length mismatch')
            continue
        if sum(b) & 0xFF:
            bad_ck += 1
            if len(first_bad) < 5:
                first_bad.append(f'line {no}: checksum error')
        types[typ] += 1
        d = b[4:4 + n]
        if typ == 0:
            chunks.append((base + addr, n)); total += n
            reclens[n] += 1
            if len(addrs) < 200000:
                addrs.append(base + addr)
            if len(blob) < 4_000_000:
                blob += d
        elif typ == 1:
            eof = True
        elif typ == 2 and n == 2:
            base = ((d[0] << 8) | d[1]) << 4
        elif typ == 4 and n == 2:
            base = ((d[0] << 8) | d[1]) << 16
        elif typ == 3 and n == 4:
            entry = f'CS:IP {d[0] << 8 | d[1]:04X}:{d[2] << 8 | d[3]:04X}'
        elif typ == 5 and n == 4:
            entry = f'0x{int.from_bytes(d, "big"):08X}'
    word_init = bool(reclens and len(reclens) == 1 and next(iter(reclens)) <= 4 and len(addrs) > 4
                     and all(addrs[i + 1] - addrs[i] == 1 for i in range(min(200, len(addrs) - 1))))
    if word_init:
        rs = _ranges([(a, 1) for a in addrs])
    else:
        rs = _ranges(chunks)
    unit = 'words' if word_init else 'bytes'
    meta = [('Records', f'{nrec:,}'), ('Data bytes', f'{total:,}'), ('Address ranges', len(rs))]
    if rs:
        lo, hi = rs[0][0], rs[-1][0] + rs[-1][1] - 1
        meta.append(('Lowest / highest address', f'0x{lo:X} / 0x{hi:X}' + (' (word addresses)' if word_init else '')))
        meta.append(('Ranges', '; '.join(_fmt_ranges(rs, unit=unit)[:40]) + (f' … {len(rs) - 40} more' if len(rs) > 40 else '')))
    if entry:
        meta.append(('Entry point', entry))
    meta.append(('Checksum errors', bad_ck))
    if bad_fmt:
        meta.append(('Malformed lines', bad_fmt))
    meta.append(('EOF record', 'present' if eof else 'MISSING'))
    rec_names = {0: 'data', 1: 'EOF', 2: 'ext. segment addr', 3: 'start segment addr', 4: 'ext. linear addr', 5: 'start linear addr'}
    meta.append(('Record types', ', '.join(f'{rec_names.get(t, t)} ×{c:,}' for t, c in sorted(types.items()))))
    notes = []
    target = ''
    # FPGA / memory-init style: tiny equal records, addresses step by 1 (word addressed)
    low_path = path.lower()
    if word_init:
        w = next(iter(reclens))
        target = f'word-addressed memory initialisation file ({len(addrs):,} words × {w * 8} bits — FPGA ROM/RAM init, e.g. Quartus)'
    elif re.search(r'altera|fpga|quartus|xilinx|cyclone|stratix|epcs', low_path):
        target = 'FPGA configuration / flash image (FPGA project folder)'
    else:
        if any(0x4000 <= a <= 0x4010 for a, n in rs) and rs[0][0] + rs[0][1] <= 0x4000:
            target = 'Microchip PIC16 (configuration word at 0x2007)'
        elif any(a >= 0x300000 and a < 0x300010 for a, _ in rs):
            target = 'Microchip PIC18 (configuration bytes at 0x300000)'
        elif any(a >= 0x1FC00000 for a, _ in rs) and any(a >= 0x1D000000 for a, _ in rs):
            target = 'Microchip PIC32'
        elif any(0x08000000 <= a < 0x08200000 for a, _ in rs):
            target = 'ARM Cortex-M (STM32-style flash at 0x08000000)'
        elif any(0x1E000 <= a <= 0x1FFFF for a, _ in rs) and rs[0][0] < 0x1E000:
            target = 'Possibly AVR application + bootloader section'
    if target:
        meta.append(('Probable target', target))
    strs = _strings(bytes(blob), 5, strict=True)
    outline = []
    if first_bad:
        outline += [{'heading': 'Problems'}] + first_bad
    if strs:
        outline += [{'heading': f'Embedded ASCII strings ({len(strs)})'}] + [f'`{s}`' for s in strs[:120]]
    if after_eof:
        notes.append(f'{after_eof} non-empty lines after the EOF record were ignored.')
    shown = ', '.join(f'0x{a:04X}-0x{a + n - 1:04X}' for a, n in rs[:4]) + (' …' if len(rs) > 4 else '')
    kind = 'Intel HEX memory-init image' if word_init else 'Intel HEX firmware image'
    summ = f'{kind}, {total:,} data bytes in {len(rs)} range{"s" if len(rs) != 1 else ""}' + (f' {shown}' if rs else '') + (' (word addresses)' if word_init else '') + '.'
    if target:
        summ += f' Probable target: {target}.'
    summ += f' {nrec:,} records, ' + ('no checksum errors' if not bad_ck else f'{bad_ck} checksum errors') + (', EOF present.' if eof else ', EOF record missing.')
    if entry:
        summ += f' Entry point {entry}.'
    return {'kind': 'data', 'type': kind, 'summary': summ, 'meta': meta, 'outline': outline, 'notes': notes,
            'keywords': ['Intel HEX', 'memory init' if word_init else 'firmware'] + strs[:5]}


def _srec(path, text):
    chunks, total, bad_ck, bad_fmt, nrec = [], 0, 0, 0, 0
    header, entry, count_rec = '', None, None
    types = collections.Counter()
    blob = bytearray()
    alen = {'1': 2, '2': 3, '3': 4, '5': 2, '6': 3, '7': 4, '8': 3, '9': 2, '0': 2}
    for ln in text.split('\n'):
        ln = ln.strip()
        if not ln:
            continue
        if not re.match(r'^S[0-9][0-9A-Fa-f]+$', ln):
            bad_fmt += 1; continue
        t = ln[1]
        try:
            b = bytes.fromhex(ln[2:])
        except ValueError:
            bad_fmt += 1; continue
        nrec += 1
        if b[0] != len(b) - 1:
            bad_fmt += 1; continue
        if (sum(b[:-1]) & 0xFF) ^ 0xFF != b[-1]:
            bad_ck += 1
        types['S' + t] += 1
        al = alen.get(t, 2)
        addr = int.from_bytes(b[1:1 + al], 'big')
        d = b[1 + al:-1]
        if t == '0':
            header = d.decode('ascii', 'replace').strip('\x00 ')
        elif t in '123':
            chunks.append((addr, len(d))); total += len(d)
            if len(blob) < 4_000_000:
                blob += d
        elif t in '56':
            count_rec = addr
        elif t in '789':
            entry = f'0x{addr:0{al * 2}X}'
    rs = _ranges(chunks)
    meta = [('Records', f'{nrec:,}'), ('Data bytes', f'{total:,}'), ('Address ranges', len(rs)),
            ('Checksum errors', bad_ck), ('Record types', ', '.join(f'{k} ×{v:,}' for k, v in sorted(types.items())))]
    if header:
        meta.insert(0, ('S0 header', f'`{header[:80]}`'))
    if entry:
        meta.append(('Entry point', entry))
    if count_rec is not None:
        meta.append(('Record count (S5/S6)', count_rec))
    if bad_fmt:
        meta.append(('Malformed lines', bad_fmt))
    strs = _strings(bytes(blob), 5, strict=True)
    meta.append(('Ranges', '; '.join(_fmt_ranges(rs)[:40]) + (f' … {len(rs) - 40} more' if len(rs) > 40 else '')))
    outline = []
    if strs:
        outline += [{'heading': f'Embedded ASCII strings ({len(strs)})'}] + [f'`{s}`' for s in strs[:120]]
    shown = ', '.join(f'0x{a:04X}-0x{a + n - 1:04X}' for a, n in rs[:4]) + (' …' if len(rs) > 4 else '')
    summ = f'Motorola S-record firmware image, {total:,} data bytes in {len(rs)} range{"s" if len(rs) != 1 else ""} {shown}.'
    if header:
        summ += f' Header: "{header[:60]}".'
    if entry:
        summ += f' Entry point {entry}.'
    summ += ' ' + ('No checksum errors.' if not bad_ck else f'{bad_ck} checksum errors.')
    return {'kind': 'data', 'type': 'Motorola S-record firmware image', 'summary': summ, 'meta': meta, 'outline': outline,
            'keywords': ['S-record', 'firmware'] + ([header] if header else []) + strs[:5]}


# ====================================================================== linker maps / reports
def _map(path, text, notes):
    head = text[:3000]
    if re.match(r'\s*<(area|map)\b', head, re.I):
        return _doxy_map(path, text)
    if re.search(r'^Release [\d.]+ Map\b|Xilinx Map Application', head, re.M):
        return _report(path, text, notes, 'Xilinx ISE MAP report', r'Target Device\s*:\s*(\S+)')
    if re.search(r'Quartus|Analysis & Synthesis|Fitter', head):
        return _report(path, text, notes, 'Altera Quartus report', r'Device\s*:\s*(\S+)')
    if head.startswith('%%% protect'):
        return {'kind': 'data', 'type': 'encrypted/protected vendor file', 'summary': 'Protected (encrypted) vendor IP map file; no readable content.',
                'notes': ['Content is vendor-encrypted.']}
    if re.match(r'\s*BLOCK\s+START ADDRESS\s+END ADDRESS', head):
        r = _generic(path, text, typ='Altera Quartus Convert Programming File memory map', notes=notes)
        m = re.findall(r'^(\w+)\s+(0x[0-9A-Fa-f]+)\s+(0x[0-9A-Fa-f]+)', text, re.M)
        if m:
            r['outline'] = [{'heading': 'Blocks'}] + [f'`{a}` {b}–{c} ({int(c, 16) - int(b, 16) + 1:,} bytes)' for a, b, c in m]
            r['summary'] = 'Altera programming-file conversion map: ' + '; '.join(f'{a} {b}–{c}' for a, b, c in m[:4]) + '.'
        return r
    return _linker_map(path, text, notes)


def _doxy_map(path, text):
    nodes = re.findall(r'<area\b[^>]*?href="\$?([^"#]*)(?:#[^"]*)?"[^>]*?title="([^"]*)"', text, re.I)
    if not nodes:
        nodes = [(h, t) for t, h in re.findall(r'<area\b[^>]*?title="([^"]*)"[^>]*?href="\$?([^"#]*)', text, re.I)]
    base = os.path.basename(path)
    kind = 'caller graph' if '_icgraph' in base else 'call graph' if '_cgraph' in base else \
        'include-dependency graph' if '_dep__incl' in base else 'include graph' if '_incl' in base else \
        'inheritance/collaboration graph' if ('coll' in base or 'inherit' in base) else 'graph'
    src = ''
    m = re.match(r'^(.*?)_8([a-z]+)_', base)
    if m:
        src = m.group(1).replace('_8', '.').replace('__', '_') + '.' + m.group(2)
    outline = [{'heading': f'Graph nodes ({len(nodes)})'}]
    seen = []
    for href, title in nodes:
        f = href.replace('.html', '').replace('_8', '.').replace('__', '_')
        item = f'`{title}`' + (f' — in `{f}`' if f and f != title else '')
        if item not in seen:
            seen.append(item)
    outline += seen[:300]
    titles = list(dict.fromkeys(t for _, t in nodes))
    summ = f'Doxygen {kind} image map' + (f' for a function in {src}' if src and 'graph' in kind and 'include' not in kind else (f' for {src}' if src else '')) + \
        f': {len(titles)} linked node{"s" if len(titles) != 1 else ""}' + (': ' + ', '.join(titles[:20]) + (' …' if len(titles) > 20 else '') if titles else '') + '.'
    return {'kind': 'data', 'type': f'Doxygen HTML image map ({kind})', 'summary': summ, 'outline': outline,
            'keywords': titles[:10] + ([src] if src else []), 'meta': [('Nodes', len(nodes))] + ([('Documented file', f'`{src}`')] if src else [])}


def _report(path, text, notes, typ, devrx):
    r = _generic(path, text, typ=typ, notes=notes)
    meta = []
    m = re.search(devrx, text[:20000])
    if m:
        meta.append(('Target device', m.group(1)))
    m = re.search(r'Xilinx Map Application Log File for Design \'([^\']+)\'', text[:2000])
    if m:
        meta.append(('Design', m.group(1)))
    m = re.search(r'^Release\s+(\S+)', text[:200], re.M)
    if m:
        meta.append(('Tool release', m.group(1)))
    nw = len(re.findall(r'^WARNING:', text, re.M)); ne = len(re.findall(r'^ERROR:', text, re.M)); ni = len(re.findall(r'^INFO:', text, re.M))
    meta.append(('Errors / warnings / info', f'{ne} / {nw} / {ni}'))
    util = re.findall(r'^\s+(Number of [^:]+?):\s+([\d,]+)\s+out of\s+([\d,]+)\s+(\d+%)', text, re.M)
    if util:
        r['outline'] = [{'heading': 'Device utilisation'}] + [f'{a}: {b} of {c} ({d})' for a, b, c, d in util[:60]]
    r['meta'] = meta
    dev = meta[0][1] if meta and meta[0][0] == 'Target device' else ''
    s = f'{typ}' + (f" for design {dict(meta).get('Design')}" if dict(meta).get('Design') else '') + (f' targeting {dev}' if dev else '') + f': {ne} errors, {nw} warnings.'
    if util:
        s += ' ' + '; '.join(f'{a.replace("Number of ", "")} {b}/{c} ({d})' for a, b, c, d in util[:4]) + '.'
    r['summary'] = s
    r['keywords'] = [x for x in (dev, dict(meta).get('Design')) if x]
    return r


SYM_LINE_RES = [
    # MPLINK:  name  0x0001fc  program  static  file
    re.compile(r'^\s*([A-Za-z_.$?][\w.$?@]*)\s+0x([0-9a-fA-F]+)\s+(program|data|eeprom|code)\s+(static|extern|global)\b(?:\s+(\S.*))?$'),
    # ADI:  name  PM  0200bc  static
    re.compile(r'^\s*([A-Za-z_.$?][\w.$?@]*)\s+(PM|DM|IO)\s+([0-9a-fA-F]{4,8})\s+(static|global|local|extern)\b'),
    # GNU ld:   0x08000000      Reset_Handler
    re.compile(r'^\s+0x([0-9a-fA-F]{4,16})\s+([A-Za-z_.$][\w.$@]*)\s*$'),
    # generic:  name   addr  (hex with h suffix or 0x)
    re.compile(r'^\s*([A-Za-z_.$?][\w.$?@]{1,60})\s+(?:=\s*)?(?:0x)?([0-9a-fA-F]{2,8})h?\s*(?:\S+\s*)?$'),
]


def _linker_map(path, text, notes):
    head = text[:4000]
    tool = ''
    for rx, nm in [(r'Microchip MPLAB XC8 Compiler\s*V?([\d.]+)', 'Microchip MPLAB XC8 {}'), (r'MPLINK\s+([\d.]+)', 'Microchip MPLINK {}'),
                   (r'Analog Devices (ADSP-\S+) Linker', 'Analog Devices {} linker'), (r'(Memory Configuration)', 'GNU ld'),
                   (r'IAR (?:Universal|ELF) Linker\s*V?([\d.]+)', 'IAR linker {}'), (r'(ImageCraft)', 'ImageCraft'),
                   (r'(BL51|LX51)[^\n]*?V([\d.]+)', 'Keil {}'), (r'VisualDSP\+\+', 'ADI VisualDSP++ linker'),
                   (r'(Archive member included)', 'GNU ld'), (r'(SmartLinker\s+V-?[\d.]+)', 'Freescale/Metrowerks {}')]:
        m = re.search(rx, head, re.I)
        if m:
            tool = nm.format(*m.groups()) if '{}' in nm else nm
            break
    lines = text.split('\n')
    syms = []
    seen = set()
    regions, sections = [], []
    sym_line = set()
    for i, ln in enumerate(lines):
        for k, rx in enumerate(SYM_LINE_RES[:3]):
            m = rx.match(ln)
            if m:
                if k == 0:
                    nm, addr, extra = m.group(1), '0x' + m.group(2), f'{m.group(3)}, {m.group(4)}'
                elif k == 1:
                    nm, addr, extra = m.group(1), '0x' + m.group(3), f'{m.group(2)}, {m.group(4)}'
                else:
                    nm, addr, extra = m.group(2), '0x' + m.group(1), ''
                sym_line.add(i)
                if nm not in seen:
                    seen.add(nm); syms.append((nm, addr, extra))
                break
        # GNU memory config: name  origin  length  attrs
        m = re.match(r'^(\w+)\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)(\s+\w+)?\s*$', ln)
        if m and tool == 'GNU ld':
            regions.append((m.group(1), int(m.group(2), 16), int(m.group(3), 16), (m.group(4) or '').strip()))
            sym_line.add(i)
        m = re.match(r'^(\.[\w.]+)\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)', ln)
        if m and tool == 'GNU ld':
            sections.append((m.group(1), int(m.group(2), 16), int(m.group(3), 16)))
        # ADI / generic segment tables: seg  start end length type
        m = re.match(r'^(seg_\w+|\w+)\s+([0-9a-fA-F]{6,8}|\*+)\s+([0-9a-fA-F]{6,8}|\*+)\s+(\d+)\s+(.+?)\s*$', ln)
        if m:
            sections.append((m.group(1), m.group(2), m.group(3), int(m.group(4)), m.group(5)))
            sym_line.add(i)
        # MPLINK section info: .name  type  0xaddr  location  0xsize
        m = re.match(r'^\s*(\S+)\s+(code|romdata|udata|idata|udata_acs|udata_ovr|udata_shr)\s+0x([0-9a-fA-F]+)\s+(program|data)\s+0x([0-9a-fA-F]+)\s*$', ln)
        if m:
            sections.append((m.group(1), int(m.group(3), 16), int(m.group(5), 16), m.group(2), m.group(4)))
            sym_line.add(i)
        # XC8 psect table: name link load length selector space
        m = re.match(r'^\s{8,}(\w+)\s+([0-9A-F]+)\s+([0-9A-F]+)\s+([0-9A-F]+)\s+([0-9A-F]+)\s+(\d)(?:\s+\d)?\s*$', ln)
        if m and 'XC8' in tool:
            sections.append((m.group(1), int(m.group(2), 16), int(m.group(4), 16), f'space {m.group(6)}'))
            sym_line.add(i)
    meta = [('Linker', tool or 'unknown')]
    m = re.search(r'Machine type is\s+(\S+)', text[:20000])
    if m:
        meta.append(('Machine type', m.group(1)))
    m = re.search(r'Architecture Description:\s*(\S+)', text[:5000])
    if m:
        meta.append(('Architecture', m.group(1)))
    m = re.search(r'(\d+) out of (\d+) program addresses used, program memory utilization is (\d+%)', text)
    if m:
        meta.append(('Program memory', f'{m.group(1)} of {m.group(2)} addresses ({m.group(3)})'))
    usage = re.findall(r'^\s*(Program Memory|Data Memory)\s+(ROM|RAM|PORT)\s+(\d+)\s*$', text, re.M)
    for a, b, c in usage:
        if c != '0':
            meta.append((f'{a} {b} used', f'{int(c):,} words'))
    outline = []
    if regions:
        outline.append({'heading': f'Memory regions ({len(regions)})'})
        outline += [f'`{n}` origin 0x{o:X}, length {_kb(l)}' + (f' ({a})' if a else '') for n, o, l, a in regions[:60]]
    if sections:
        outline.append({'heading': f'Sections / segments ({len(sections)})'})
        for s in sections[:150]:
            if len(s) == 3:
                outline.append(f'`{s[0]}` at 0x{s[1]:X}, size {s[2]:,} bytes')
            elif len(s) == 5 and isinstance(s[1], str):
                outline.append(f'`{s[0]}` {s[1]}–{s[2]}, {s[3]:,} words, {s[4]}')
            elif len(s) == 5:
                outline.append(f'`{s[0]}` {s[3]} at 0x{s[1]:X} in {s[4]}, {s[2]:,} bytes')
            else:
                outline.append(f'`{s[0]}` at 0x{s[1]:X}, length 0x{s[2]:X} ({s[3]})')
    if syms:
        outline.append({'heading': f'Symbols ({len(syms):,}{", first 200" if len(syms) > 200 else ""})'})
        outline += [f'`{n}` {a}' + (f' ({e})' if e else '') for n, a, e in syms[:200]]
    # paragraphs: non-tabular blocks
    pars = []
    for block in re.split(r'\n\s*\n', text):
        bl = [l for l in block.split('\n') if l.strip()]
        if not bl:
            continue
        tab = sum(1 for l in bl if re.search(r'0x[0-9a-fA-F]{3,}|\b[0-9a-fA-F]{5,8}\b', l))
        if tab / len(bl) > 0.5 and len(bl) > 2:
            continue
        pars.append('\n'.join(l.rstrip() for l in bl))
    pars = _cap_pars(pars, notes)
    notes.append('Tabular address listings are summarised in Structure; only descriptive text is reproduced.')
    # summary
    s = f'{tool or "Linker"} map'
    m = re.search(r'-M\S*?([\w.\-]+)\.map|(\S+?)\.map', os.path.basename(path))
    s += f' for {os.path.basename(path)[:-4]}'
    bits = []
    if 'GNU' in tool and sections:
        sz = collections.Counter()
        for n, a, l in [x for x in sections if len(x) == 3]:
            key = 'text' if n.startswith(('.text', '.rodata', '.init', '.fini', '.vectors', '.isr')) else 'data' if n.startswith('.data') else 'bss' if n.startswith(('.bss', '.noinit', '.stack', '.heap')) else None
            if key:
                sz[key] += l
        bits = [f'{k} {_kb(v)}' for k, v in sz.items() if v]
    elif sections and len(sections[0]) == 5 and isinstance(sections[0][1], str):
        bits = [f'{x[0]} {x[3]:,} words' for x in sections if x[3]][:6]
    elif sections:
        bits = [f'{x[0]} {x[2]:,} bytes' for x in sections if len(x) >= 3 and isinstance(x[2], int) and x[2]][:6]
    for k, v in meta[1:]:
        if k in ('Program memory', 'Machine type', 'Architecture'):
            bits.append(f'{k.lower()} {v}')
    if bits:
        s += ': ' + ', '.join(bits)
    s += f'; {len(syms):,} symbols.' if syms else '.'
    return {'kind': 'data', 'type': (tool + ' map' if tool.endswith('linker') else f'{tool + " " if tool else ""}linker map'), 'summary': s, 'meta': meta, 'outline': outline,
            'paragraphs': pars, 'notes': notes, 'keywords': [n for n, _, _ in syms[:8]]}


def _kb(n):
    if n >= 1024 * 1024 and n % (1024 * 1024) == 0:
        return f'{n // (1024 * 1024)} MB'
    if n >= 1024:
        return f'{n / 1024:.1f} KB'.replace('.0 KB', ' KB')
    return f'{n} bytes'


# ====================================================================== linker scripts
def _strip_c_comments(text):
    comments = []

    def rep(m):
        comments.append(m.group(0))
        return '\n' * m.group(0).count('\n')
    t = re.sub(r'/\*.*?\*/', rep, text, flags=re.S)
    t = re.sub(r'//[^\n]*', rep, t)
    return t, comments


def _parse_size(s):
    s = s.strip()
    m = re.match(r'^(0x[0-9a-fA-F]+|\d+)\s*([KkMm])?$', s)
    if not m:
        return None
    v = int(m.group(1), 0)
    if m.group(2):
        v *= 1024 if m.group(2).lower() == 'k' else 1024 * 1024
    return v


def _linker_script(path, text, ext, notes):
    if ext == 'lk' and not re.search(r'\b(SECTIONS|MEMORY)\b|^\s*-', text, re.M):
        objs = re.findall(r'[^\s]+\.(?:o|a|lib|obj)\b', text)
        opts = re.findall(r'(?:^|\s)(-\S+)', text)
        outline = [{'heading': f'Linked objects ({len(objs)})'}] + [f'`{o}`' for o in objs]
        if opts:
            outline += [{'heading': 'Options'}] + [f'`{o}`' for o in opts]
        summ = f'ImageCraft linker object list: {len(objs)} object file{"s" if len(objs) != 1 else ""}' + (': ' + ', '.join(objs[:25]) + (' …' if len(objs) > 25 else '') if objs else '') + '.'
        return {'kind': 'data', 'type': 'ImageCraft ICCAVR linker object list', 'summary': summ, 'outline': outline,
                'keywords': [o.rsplit('.', 1)[0] for o in objs[:12]], 'meta': [('Objects', len(objs))]}
    code, comments = _strip_c_comments(text)
    if ext == 'xcl':
        return _xcl(path, text, code, comments, notes)
    outline, meta = [], []
    regions = []
    typ = 'GNU ld linker script'
    if ext == 'ldf' or re.search(r'^\s*ARCHITECTURE\s*\(', code, re.M):
        typ = 'ADI VisualDSP++ linker description file (LDF)'
        m = re.search(r'ARCHITECTURE\s*\(\s*([\w\-]+)\s*\)', code)
        if m:
            meta.append(('Architecture', m.group(1)))
        for m in re.finditer(r'(\w+)\s*\{\s*TYPE\s*\(([^)]*)\)\s*START\s*\(\s*(\w+)\s*\)\s*END\s*\(\s*(\w+)\s*\)\s*WIDTH\s*\(\s*(\d+)\s*\)', code):
            s, e = int(m.group(3), 0), int(m.group(4), 0)
            regions.append(f'`{m.group(1)}` {m.group(2).strip()} 0x{s:08X}–0x{e:08X} ({e - s + 1:,} words × {m.group(5)} bits)')
        procs = re.findall(r'^\s*PROCESSOR\s+(\w+)', code, re.M)
        if procs:
            meta.append(('Processors', ', '.join(procs)))
        secs = re.findall(r'^\s*(\w+)\s*(?:\w+\s*)?\{\s*INPUT_SECTIONS\s*\(([^)]*)\)[^}]*\}\s*>\s*(\w+)', code, re.M)
        sec_items = [f'`{a}` → `{c}` (inputs: {b.strip()[:80]})' for a, b, c in secs]
        for k, rx in [('Search dirs', r'SEARCH_DIR\s*\(([^)]*)\)'), ('Libraries', r'\$LIBRARIES\s*=\s*([^;]+);'), ('Objects', r'\$OBJECTS\s*=\s*([^;]+);')]:
            v = re.findall(rx, code)
            if v:
                meta.append((k, '`' + ', '.join(x.strip() for x in v)[:200] + '`'))
    elif ext == 'icf' or re.search(r'define\s+(symbol|region|memory)\b', code):
        typ = 'IAR ILINK configuration file (ICF)'
        syms = re.findall(r'define\s+(?:exported\s+)?symbol\s+(\w+)\s*=\s*([^;]+);', code)
        sv = {a: b.strip() for a, b in syms}

        def ev(x):
            x = x.strip()
            x = sv.get(x, x)
            try:
                return int(x, 0)
            except Exception:
                return None
        for m in re.finditer(r'define\s+region\s+(\w+)\s*=\s*mem\s*:\s*\[\s*from\s+([^\s\]]+)\s+(to|size)\s+([^\s\]]+)\s*\]', code):
            a, b = ev(m.group(2)), ev(m.group(4))
            if a is not None and b is not None:
                size = (b - a + 1) if m.group(3) == 'to' else b
                regions.append(f'`{m.group(1)}` 0x{a:08X}, {_kb(size)}')
            else:
                regions.append(f'`{m.group(1)}` from {m.group(2)} {m.group(3)} {m.group(4)}')
        blocks = re.findall(r'define\s+block\s+(\w+)\s+with\s+([^{;]+)', code)
        places = re.findall(r'place\s+(at\s+[^{]+|in\s+\w+)\s*\{([^}]*)\}', code)
        sec_items = [f'block `{a}` {b.strip()}' for a, b in blocks] + [f'place {a.strip()}: {b.strip()[:80]}' for a, b in places]
        if syms:
            outline.append({'heading': f'Symbols ({len(syms)})'})
            outline += [f'`{a}` = `{b.strip()}`' for a, b in syms[:200]]
    else:
        m = re.search(r'MEMORY\s*\{(.*?)\}', code, re.S)
        if m:
            for r in re.finditer(r'(\w+)\s*(?:\(([^)]*)\))?\s*:\s*(?:ORIGIN|org|o)\s*=\s*([^,]+),\s*(?:LENGTH|len|l)\s*=\s*([^\n;,]+)', m.group(1)):
                sz = _parse_size(r.group(4))
                try:
                    org = int(r.group(3).strip(), 0)
                    os_ = f'0x{org:08X}'
                except Exception:
                    os_ = r.group(3).strip()
                regions.append(f'`{r.group(1)}`' + (f' ({r.group(2)})' if r.group(2) else '') + f' origin {os_}, length {_kb(sz) if sz is not None else r.group(4).strip()}')
        sec_items = []
        sm = re.search(r'SECTIONS\s*\{', code)
        if sm:
            for r in re.finditer(r'^\s*(\.?[\w.]+)\s*(?:[^\n:{]*)?:\s*(?:AT\s*\([^)]*\)\s*)?(?:ALIGN\s*\([^)]*\)\s*)?\{', code[sm.end():], re.M):
                nm = r.group(1)
                tail = code[sm.end() + r.end():sm.end() + r.end() + 6000]
                depth, j = 1, 0
                while j < len(tail) and depth:
                    if tail[j] == '{':
                        depth += 1
                    elif tail[j] == '}':
                        depth -= 1
                    j += 1
                mm = re.match(r'\s*(>\s*\w+)?\s*(AT\s*>\s*\w+)?', tail[j:])
                dest = ' '.join(x.strip() for x in mm.groups() if x) if mm else ''
                sec_items.append(f'`{nm}`' + (f' {dest}' if dest else ''))
        for k, rx in [('Entry point', r'ENTRY\s*\(\s*(\w+)\s*\)'), ('Output format', r'OUTPUT_FORMAT\s*\(([^)]*)\)'),
                      ('Output arch', r'OUTPUT_ARCH\s*\(([^)]*)\)'), ('Search dirs', r'SEARCH_DIR\s*\(([^)]*)\)'), ('Includes', r'INCLUDE\s+(\S+)')]:
            v = re.findall(rx, code)
            if v:
                meta.append((k, '`' + ', '.join(x.strip() for x in v)[:200] + '`'))
        syms = re.findall(r'^\s*(?:PROVIDE\s*\(\s*)?([A-Za-z_.][\w.]*)\s*=\s*([^;]+);', code, re.M)
        syms = [(a, b) for a, b in syms if a != '.']
        if syms:
            outline.append({'heading': f'Symbol assignments ({len(syms)})'})
            outline += [f'`{a}` = `{b.strip()[:80]}`' for a, b in syms[:200]]
    if regions:
        outline = [{'heading': f'Memory regions ({len(regions)})'}] + regions + outline
    if sec_items:
        outline += [{'heading': f'Output sections / placement ({len(sec_items)})'}] + sec_items[:200]
    pars = []
    for c in comments:
        body = _clean_doc([re.sub(r'^\s*(//+|/\*+|\*+/?)', '', l).replace('*/', '') for l in c.split('\n')])
        if body:
            if pars and c.startswith('//') and not pars[-1].endswith('\n\n'):
                pars[-1] += '\n' + body
            else:
                pars.append(body)
    pars = _cap_pars(pars, notes)
    meta.append(('Memory regions', len(regions)))
    summ = typ + (f" for {dict(meta)['Architecture']}" if 'Architecture' in dict(meta) else '') + ': '
    summ += ('memory ' + '; '.join(re.sub(r'`', '', r) for r in regions[:5]) + (' …' if len(regions) > 5 else '') if regions else 'no MEMORY regions')
    if sec_items:
        summ += f'; {len(sec_items)} output section/placement rules'
    ep = dict(meta).get('Entry point')
    if ep:
        summ += f'; entry {ep.strip("`")}'
    summ += '.'
    return {'kind': 'source', 'type': typ, 'summary': summ, 'meta': meta, 'outline': outline, 'paragraphs': pars, 'notes': notes,
            'keywords': [re.sub(r'`', '', r).split()[0] for r in regions[:8]]}


def _xcl(path, text, code, comments, notes):
    opts = [l.strip() for l in code.split('\n') if l.strip().startswith('-')]
    defs = [(m.group(1), m.group(2)) for m in (re.match(r'-D(\w+)=(\S+)', o) for o in opts) if m]
    segs = [o for o in opts if re.match(r'-[ZPQ]', o)]
    cpu = next((o[2:].strip('=') for o in opts if o.startswith('-c')), '')
    outline = []
    if defs:
        outline += [{'heading': f'Defined symbols ({len(defs)})'}] + [f'`{a}` = `{b}`' for a, b in defs[:200]]
    if segs:
        outline += [{'heading': f'Segment placement ({len(segs)})'}] + [f'`{s[:140]}`' for s in segs[:200]]
    other = [o for o in opts if not re.match(r'-[DZPQ]', o)]
    if other:
        outline += [{'heading': 'Other options'}] + [f'`{o[:140]}`' for o in other[:80]]
    pars = []
    for c in comments:
        b = _clean_doc([re.sub(r'^\s*(//+|/\*+|\*+/?)', '', l).replace('*/', '') for l in c.split('\n')])
        if b:
            pars.append(b)
    merged = []
    for p in pars:
        if merged and len(merged[-1]) < 2000:
            merged[-1] += '\n' + p
        else:
            merged.append(p)
    meta = [('CPU option', cpu or '—'), ('Symbol definitions', len(defs)), ('Segment rules', len(segs))]
    summ = f'IAR XLINK command/configuration file' + (f' for CPU {cpu}' if cpu else '') + f': {len(defs)} symbol definitions, {len(segs)} segment placement rules.'
    return {'kind': 'source', 'type': 'IAR XLINK linker command file (.xcl)', 'summary': summ, 'meta': meta,
            'outline': outline, 'paragraphs': _cap_pars(merged, notes), 'notes': notes, 'keywords': [a for a, _ in defs[:8]]}


# ====================================================================== look-alikes
def _sym(path):
    with open(path, 'rb') as f:
        data = f.read(8_000_000)
    head = data[:200]
    if head.lstrip().startswith(b'<?xml') or b'<symbol' in data[:400]:
        t = data.decode('utf-8', 'replace')
        nm = re.search(r'<symbol\b[^>]*\bname="([^"]*)"', t)
        st = re.search(r'<symboltype>([^<]*)<', t)
        ts = re.search(r'<timestamp>([^<]*)<', t)
        pins = re.findall(r'<pin\b[^>]*?polarity="([^"]*)"[^>]*?name="([^"]*)"', t)
        return _sym_result(nm.group(1) if nm else os.path.basename(path), st.group(1) if st else '', ts.group(1) if ts else '', pins, 'Xilinx ISE schematic symbol (XML)')
    if head.startswith(b'VERSION') and b'BEGIN SYMBOL' in data[:500]:
        t = data.decode('latin-1')
        nm = re.search(r'BEGIN SYMBOL\s+(\S+)', t)
        st = re.search(r'SYMBOLTYPE\s+(\S+)', t)
        ts = re.search(r'TIMESTAMP\s+(.+)', t)
        pins = [(p, n) for p, n in re.findall(r'^SYMPIN\s+-?\d+\s+-?\d+\s+(\w+)\s+(\S+)', t, re.M)]
        return _sym_result(nm.group(1) if nm else '', st.group(1) if st else '', ts.group(1).strip() if ts else '', pins, 'Xilinx schematic symbol (text, legacy)')
    if head.startswith(b'SYM'):
        strs = _strings(data, 2)
        strs = [s for s in strs if re.match(r'^[A-Za-z_][\w\[\]\.\-:/ ]*$', s)]
        r = {'kind': 'binary', 'type': 'Altera MAX+PLUS II / Quartus graphic symbol (binary .sym)',
             'meta': [('First bytes', '`' + data[:16].hex(' ') + '`')],
             'notes': ['Binary symbol format: pin/label names recovered as printable strings only.']}
        if strs:
            r['outline'] = [{'heading': f'Names in symbol ({len(strs)})'}] + [f'`{s}`' for s in strs[:200]]
            r['summary'] = f'Altera binary graphic symbol {os.path.splitext(os.path.basename(path))[0]}; names found: ' + ', '.join(strs[:25]) + (' …' if len(strs) > 25 else '') + '.'
            r['keywords'] = strs[:10]
        return r
    if core.looks_binary(path):
        return _binary(path, 'binary symbol file')
    text, trunc = _read(path)
    # debugger symbol table: name  address
    rows = re.findall(r'^\s*([A-Za-z_.$?][\w.$?@]*)\s+(?:0x)?([0-9a-fA-F]{2,8})h?\b', text, re.M)
    if len(rows) > 10 and len(rows) > 0.5 * text.count('\n'):
        outline = [{'heading': f'Symbols ({len(rows):,}, first 300)'}] + [f'`{a}` 0x{b}' for a, b in rows[:300]]
        return {'kind': 'data', 'type': 'debugger symbol table', 'outline': outline,
                'summary': f'Symbol table with {len(rows):,} entries: ' + ', '.join(a for a, _ in rows[:20]) + '.',
                'keywords': [a for a, _ in rows[:10]]}
    return _generic(path, text, notes=['File larger than 20 MB: text truncated.'] if trunc else [])


def _sym_result(name, stype, ts, pins, typ):
    ins = [n for p, n in pins if p.lower().startswith('in') and not p.lower().startswith('inout')]
    outs = [n for p, n in pins if p.lower().startswith('out')]
    bid = [n for p, n in pins if p.lower() in ('bidirectional', 'inout', 'bidir', 'bus')]
    params = [(n, p, '') for p, n in pins]
    f = {'name': name or '?', 'kind': 'schematic symbol', 'signature': f'{name}(' + ', '.join(n for _, n in pins) + ')',
         'doc': f'{stype or "Symbol"} with {len(pins)} pins.', 'params': params}
    meta = [('Symbol', name), ('Symbol type', stype or '?'), ('Pins', f'{len(pins)} ({len(ins)} in, {len(outs)} out' + (f', {len(bid)} bidir' if bid else '') + ')')]
    if ts:
        meta.append(('Timestamp', ts))
    summ = f'{typ} "{name}" ({stype or "symbol"}) with {len(pins)} pins. Inputs: ' + (', '.join(ins[:20]) or 'none') + '. Outputs: ' + (', '.join(outs[:20]) or 'none') + '.'
    if bid:
        summ += ' Bidirectional: ' + ', '.join(bid[:10]) + '.'
    return {'kind': 'source', 'type': typ, 'summary': summ, 'meta': meta, 'functions': [f],
            'keywords': [name] + [n.split('(')[0] for _, n in pins[:10]]}


def _ahdl_inc(path, text, notes):
    code = re.sub(r'--[^\n]*', '', text)
    code = re.sub(r'%.*?%', '', code, flags=re.S)
    funcs = []
    for m in re.finditer(r'\bFUNCTION\s+(\w+)\s*\((.*?)\)\s*(?:WITH\s*\((.*?)\)\s*)?RETURNS\s*\((.*?)\)\s*;', code, re.S | re.I):
        ln = code[:m.start()].count('\n') + 1
        ins = [x.strip() for x in re.split(r',(?![^\[]*\])', ' '.join(m.group(2).split())) if x.strip()]
        outs = [x.strip() for x in re.split(r',(?![^\[]*\])', ' '.join(m.group(4).split())) if x.strip()]
        prm = [x.strip() for x in re.split(r',', ' '.join((m.group(3) or '').split())) if x.strip()]
        params = [(x, 'input', '') for x in ins] + [(x, 'output', '') for x in outs] + [(x, 'parameter', '') for x in prm]
        funcs.append({'name': m.group(1), 'kind': 'AHDL function prototype', 'line': ln,
                      'signature': ' '.join(m.group(0).split()), 'params': params,
                      'returns': ', '.join(outs), 'doc': f'{len(ins)} input(s), {len(outs)} output(s)' + (f', {len(prm)} parameter(s)' if prm else '') + '.'})
    for m in re.finditer(r'^\s*define\s+(\w+)\s*\(([^)]*)\)\s*=\s*(.*?);\s*$', code, re.M | re.I):
        ln = code[:m.start()].count('\n') + 1
        funcs.append({'name': m.group(1), 'kind': 'AHDL define macro', 'line': ln, 'signature': ' '.join(m.group(0).split())[:400],
                      'params': [(x.strip(), 'argument', '') for x in m.group(2).split(',') if x.strip()]})
    meta = []
    m = re.search(r'Generated by (Quartus[^\n]*?|MAX\+plus[^\n]*?)(?:\n|$)', text)
    if m:
        meta.append(('Generated by', m.group(1).strip()))
    m = re.search(r'Created on (.+)', text)
    if m:
        meta.append(('Created', m.group(1).strip()))
    consts = re.findall(r'^\s*CONSTANT\s+(\w+)\s*=\s*([^;]+);', code, re.M | re.I)
    outline = []
    if consts:
        outline = [{'heading': 'Constants'}] + [f'`{a}` = `{b.strip()}`' for a, b in consts[:80]]
    pars = [p for p in core.split_paragraphs('\n'.join(re.sub(r'^\s*--\s?', '', l) for l in text.split('\n') if l.strip().startswith('--')))]
    pars = [p for p in pars if not re.search(r'Altera Program License|expressly subject', p)]
    protos = [f for f in funcs if f['kind'] == 'AHDL function prototype']
    defs = [f for f in funcs if f['kind'] != 'AHDL function prototype']
    gen = dict(meta).get('Generated by')
    summ = 'Altera AHDL include file' + (f' ({gen})' if gen else '')
    if protos:
        summ += ' declaring ' + '; '.join(f"{f['name']} (inputs: {_short([p[0] for p in f['params'] if p[1] == 'input'])}; outputs: {_short([p[0] for p in f['params'] if p[1] == 'output'])})" for f in protos[:6])
    if defs:
        summ += (' and' if protos else ' with') + f' {len(defs)} define macro{"s" if len(defs) != 1 else ""}: ' + _short([f['name'] for f in defs], 15)
    summ += '.'
    return {'kind': 'source', 'type': 'Altera AHDL include (function prototype)' if protos else 'Altera AHDL include (define macros)', 'summary': summ, 'meta': meta,
            'functions': funcs, 'outline': outline, 'paragraphs': pars, 'code_lang': 'ahdl', 'notes': notes,
            'keywords': [f['name'] for f in funcs[:8]]}


def _short(xs, n=12):
    return (', '.join(xs[:n]) + (f' … ({len(xs)} total)' if len(xs) > n else '')) if xs else 'none'


def _icc_project(path, text, notes):
    outline, sect = [], None
    counts = collections.OrderedDict()
    for ln in text.split('\n'):
        s = ln.strip()
        if not s:
            continue
        m = re.match(r'^\[(.+)\]$', s)
        if m:
            sect = m.group(1); counts[sect] = 0
            outline.append({'heading': sect}); continue
        if sect is not None:
            counts[sect] += 1
        outline.append(f'`{s}`')
    files = [o.strip('`') for o in outline if isinstance(o, str)]
    summ = 'ImageCraft ICCAVR project file list: ' + ', '.join(f'{k} {v}' for k, v in counts.items()) + '. Files: ' + ', '.join(files[:25]) + (' …' if len(files) > 25 else '') + '.'
    return {'kind': 'data', 'type': 'ImageCraft ICCAVR project source list (.SRC)', 'summary': summ, 'outline': outline,
            'meta': [(f'[{k}]', v) for k, v in counts.items()], 'keywords': [f.rsplit('.', 1)[0] for f in files[:10]]}


def _cspy_mac(path, text, notes):
    code, comments = _strip_c_comments(text)
    funcs = []
    for m in re.finditer(r'^\s*(?:__var\s+)?(\w+)\s*\(([^)]*)\)\s*\n?\s*\{', code, re.M):
        name = m.group(1)
        if name in ('if', 'while', 'for', 'switch'):
            continue
        ln = code[:m.start()].count('\n') + 1
        # body
        i, depth = m.end(), 1
        while i < len(code) and depth:
            depth += {'{': 1, '}': -1}.get(code[i], 0); i += 1
        body = code[m.end():i]
        calls = list(dict.fromkeys(c for c in re.findall(r'\b(\w+)\s*\(', body) if c not in ('if', 'while', 'for', 'switch', 'return')))
        lines = text.split('\n')
        doc = []
        k = ln - 2
        while k >= 0 and lines[k].strip().startswith(('//', '/*', '*')):
            doc.append(re.sub(r'^\s*(//+|/\*+|\*+/?)', '', lines[k]).strip()); k -= 1
        doc.reverse()
        params = [(p.strip(), '', '') for p in m.group(2).split(',') if p.strip()]
        funcs.append({'name': name, 'kind': 'C-SPY macro function', 'line': ln, 'signature': f'{name}({m.group(2).strip()})',
                      'doc': _clean_doc(doc), 'params': params, 'calls': calls[:60]})
    vars_ = re.findall(r'__var\s+([\w\s,]+);', code)
    outline = [{'heading': 'Macro variables'}, ', '.join(f'`{v.strip()}`' for vv in vars_ for v in vv.split(','))] if vars_ else []
    pars = []
    for c in comments:
        b = _clean_doc([re.sub(r'^\s*(//+|/\*+|\*+/?)', '', l).replace('*/', '') for l in c.split('\n')])
        if b:
            if pars and c.startswith('//'):
                pars[-1] += '\n' + b
            else:
                pars.append(b)
    hdr = next((p for p in pars if len(p) > 30 and 'warranty' not in p.lower()), '')
    summ = 'IAR Embedded Workbench C-SPY debugger macro file' + (f': {" ".join(hdr.split())[:300]}' if hdr else '') + \
        f'. {len(funcs)} macro function{"s" if len(funcs) != 1 else ""}: ' + ', '.join(f['name'] for f in funcs[:20]) + '.'
    return {'kind': 'source', 'type': 'IAR C-SPY macro file', 'summary': summ, 'functions': funcs, 'outline': outline,
            'paragraphs': _cap_pars(pars, notes), 'code_lang': 'c', 'notes': notes, 'keywords': [f['name'] for f in funcs[:8]]}
