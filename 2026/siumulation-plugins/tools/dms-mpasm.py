#!/usr/bin/env python3
"""Minimal MPASM-compatible assembler for the DMS-1 front-panel PIC sources (PIC16C73B / PIC16F73).
Supports exactly what the DMS1V100-V102 sources use: #INCLUDE, MACRO/ENDM (no parameters), EQU, ORG, RES,
END, ERRORLEVEL/LIST (ignored), case-insensitive symbols (/c-), default radix decimal (/rdec), 0x.., B'..', ..H.
Output: JSON with code words, per-address source refs, labels, RAM symbols, cycle info."""
import sys, os, re, json

SFR = dict(INDF=0, TMR0=1, PCL=2, STATUS=3, FSR=4, PORTA=5, PORTB=6, PORTC=7, PCLATH=0x0A, INTCON=0x0B, PIR1=0x0C,
           PIR2=0x0D, TMR1L=0x0E, TMR1H=0x0F, T1CON=0x10, TMR2=0x11, T2CON=0x12, SSPBUF=0x13, SSPCON=0x14, CCPR1L=0x15,
           CCPR1H=0x16, CCP1CON=0x17, RCSTA=0x18, TXREG=0x19, RCREG=0x1A, CCPR2L=0x1B, CCPR2H=0x1C, CCP2CON=0x1D,
           ADRES=0x1E, ADCON0=0x1F, OPTION_REG=0x81, TRISA=0x85, TRISB=0x86, TRISC=0x87, PIE1=0x8C, PIE2=0x8D,
           PCON=0x8E, PR2=0x92, SSPADD=0x93, SSPSTAT=0x94, TXSTA=0x98, SPBRG=0x99, ADCON1=0x9F,
           W=0, F=1, C=0, DC=1, Z=2, RP0=5, RP1=6, IRP=7, PCFG0=0, PCFG1=1, PCFG2=2, RCIF=5, TXIF=4, TRMT=1,
           CREN=4, SPEN=7, OERR=1, FERR=2, TXEN=5, BRGH=2, SYNC=4)

BYTE_OPS = dict(ADDWF=0x0700, ANDWF=0x0500, COMF=0x0900, DECF=0x0300, DECFSZ=0x0B00, INCF=0x0A00, INCFSZ=0x0F00,
                IORWF=0x0400, MOVF=0x0800, RLF=0x0D00, RRF=0x0C00, SUBWF=0x0200, SWAPF=0x0E00, XORWF=0x0600)
BIT_OPS = dict(BCF=0x1000, BSF=0x1400, BTFSC=0x1800, BTFSS=0x1C00)
LIT_OPS = dict(ADDLW=0x3E00, ANDLW=0x3900, IORLW=0x3800, MOVLW=0x3000, RETLW=0x3400, SUBLW=0x3C00, XORLW=0x3A00)
FIXED = dict(CLRW=0x0100, NOP=0x0000, CLRWDT=0x0064, RETFIE=0x0009, RETURN=0x0008, SLEEP=0x0063)
MNEM = set(BYTE_OPS) | set(BIT_OPS) | set(LIT_OPS) | set(FIXED) | {'CLRF', 'MOVWF', 'CALL', 'GOTO'}

def strip_comment(s):
    out, q = '', False
    for ch in s:
        if ch == "'" : q = not q
        if ch == ';' and not q: break
        out += ch
    return out

class Asm:
    def __init__(self, folder, main):
        self.folder = folder; self.files = []; self.lines = []   # (fileidx, lineno, text)
        self.load(main)
    def find(self, name):
        for f in os.listdir(self.folder):
            if f.lower() == name.lower(): return os.path.join(self.folder, f)
        return None
    def load(self, name):
        p = self.find(name)
        if p is None:
            if name.upper().startswith('P16'): return  # processor header -> builtin SFR table
            raise SystemExit('missing include ' + name)
        fi = len(self.files); self.files.append(os.path.basename(p))
        raw = open(p, 'rb').read().decode('latin-1').replace('\r', '').split('\n')
        for i, t in enumerate(raw):
            body = strip_comment(t).strip()
            m = re.match(r'#include\s+"([^"]+)"', body, re.I)
            if m: self.load(m.group(1)); continue
            self.lines.append((fi, i + 1, t))
            if re.match(r'^\s*END\s*$', strip_comment(t), re.I) and fi == 0: break

    def num(self, tok, syms):
        t = tok.strip()
        if not t: raise ValueError('empty')
        m = re.fullmatch(r"[bB]'([01]+)'", t)
        if m: return int(m.group(1), 2)
        m = re.fullmatch(r"[dD]'(\d+)'", t)
        if m: return int(m.group(1))
        if re.fullmatch(r'0[xX][0-9a-fA-F]+', t): return int(t, 16)
        if re.fullmatch(r'[0-9][0-9a-fA-F]*[hH]', t): return int(t[:-1], 16)
        if re.fullmatch(r'\d+', t): return int(t)
        # simple + / - expressions
        m = re.fullmatch(r'(.+?)([+-])(.+)', t)
        if m and not re.fullmatch(r'[A-Za-z_]\w*', t):
            a, b = self.num(m.group(1), syms), self.num(m.group(3), syms)
            return a + b if m.group(2) == '+' else a - b
        u = t.upper()
        if u in syms: return syms[u]
        if u in SFR: return SFR[u]
        raise KeyError(t)

    def expand(self):
        """macro expansion -> list of (fileidx, line, label, op, args, viaMacro)"""
        macros = {}; out = []; cur = None
        for fi, ln, t in self.lines:
            s = strip_comment(t)
            if not s.strip():
                continue
            label = None
            if s[0] not in ' \t':
                parts = s.split(None, 1); label = parts[0].rstrip(':'); rest = parts[1] if len(parts) > 1 else ''
            else: rest = s.strip()
            toks = rest.split(None, 1); op = toks[0].upper() if toks else ''; args = toks[1].strip() if len(toks) > 1 else ''
            if cur is not None:
                if op == 'ENDM' or (label and label.upper() == 'ENDM'): macros[cur[0]] = cur[1]; cur = None
                else: cur[1].append((fi, ln, label, op, args))
                continue
            if op == 'MACRO': cur = (label.upper(), []); continue
            # label that is actually a mnemonic/macro written in column 1? (not used in these sources)
            out.append((fi, ln, label, op, args, None))
        res = []
        for fi, ln, label, op, args, _ in out:
            if op in macros:
                if label: res.append((fi, ln, label, '', '', None))
                for (mfi, mln, ml, mop, margs) in macros[op]:
                    res.append((mfi, mln, None, mop, margs, (fi, ln, op)))
            else:
                res.append((fi, ln, label, op, args, None))
        self.macros = macros
        return res

    def run(self):
        items = self.expand()
        for pas in (1, 2):
            syms = {} if pas == 1 else self.syms
            pc = 0; code = {}; refs = {}; ram = {}; labels = {}
            for fi, ln, label, op, args, via in items:
                if op == 'EQU':
                    syms[label.upper()] = self.num(args, syms) if pas == 2 or True else 0; continue
                if label:
                    if pas == 1: syms[label.upper()] = pc
                    if op == 'RES' or (op == '' and pc >= 0x20 and pc < 0x80 and False): pass
                if op in ('', 'ERRORLEVEL', 'LIST', 'END', 'ENDM'):
                    if label and pas == 2: labels[label] = pc
                    continue
                if op == 'ORG': pc = self.num(args, syms); continue
                if op == 'RES':
                    if label and pas == 2: ram[label] = pc
                    pc += self.num(args, syms); continue
                if label and pas == 2: labels[label] = pc
                if op not in MNEM: raise SystemExit(f'unknown op {op} at {self.files[fi]}:{ln}')
                if pas == 2:
                    a = [x.strip() for x in args.split(',')] if args else []
                    def F(x): return self.num(x, syms) & 0x7F
                    def D(i):
                        if len(a) <= i: return 1
                        return 1 if self.num(a[i], syms) else 0
                    if op in BYTE_OPS: w = BYTE_OPS[op] | (D(1) << 7) | F(a[0])
                    elif op in BIT_OPS: w = BIT_OPS[op] | ((self.num(a[1], syms) & 7) << 7) | F(a[0])
                    elif op in LIT_OPS: w = LIT_OPS[op] | (self.num(a[0], syms) & 0xFF)
                    elif op in FIXED: w = FIXED[op]
                    elif op == 'CLRF': w = 0x0180 | F(a[0])
                    elif op == 'MOVWF': w = 0x0080 | F(a[0])
                    elif op == 'CALL': w = 0x2000 | (self.num(a[0], syms) & 0x7FF)
                    elif op == 'GOTO': w = 0x2800 | (self.num(a[0], syms) & 0x7FF)
                    if pc in code: raise SystemExit(f'overlap at {pc}')
                    code[pc] = w; refs[pc] = [fi, ln] + ([via[0], via[1]] if via else [])
                pc += 1
            if pas == 1: self.syms = syms
        self.code, self.refs, self.ram, self.labels = code, refs, ram, labels
        return self

def hexwords(path):
    mem = {}; base = 0
    for line in open(path):
        line = line.strip()
        if not line.startswith(':'): continue
        b = bytes.fromhex(line[1:]); n, addr, typ = b[0], (b[1] << 8) | b[2], b[3]
        if typ == 4: base = ((b[4] << 8) | b[5]) << 16; continue
        if typ != 0: continue
        for i in range(0, n, 2):
            mem[(base + addr + i) // 2] = b[4 + i] | (b[5 + i] << 8)
    return mem

if __name__ == '__main__':
    folder, main = sys.argv[1], sys.argv[2]
    a = Asm(folder, main).run()
    print(len(a.code), 'words, last', hex(max(a.code)), 'RAM', len(a.ram), hex(max(a.ram.values())))
    if len(sys.argv) > 3:
        h = hexwords(sys.argv[3]); diff = [k for k in set(h) | set(a.code) if h.get(k) != a.code.get(k)]
        print('hex words', len(h), 'diffs', len(diff), sorted(diff)[:20])
        for k in sorted(diff)[:10]: print(hex(k), hex(h.get(k, -1)), hex(a.code.get(k, -1)), a.refs.get(k))
