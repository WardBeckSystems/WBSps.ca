"""Shared helpers for the WBS - DATA SHUFFLER sidecar generator.

Extractor contract (extractors/<family>.py)
------------------------------------------
    EXTS = {'pdf', ...}          # lowercase extensions (no dot) this module handles;
                                 # use '' for files with no extension
    NAMES = {'makefile', ...}    # optional: lowercase exact file names handled
    def extract(path: str) -> dict

`extract` returns a dict; every key is optional:
    kind        'document' | 'source' | 'data' | 'binary'
    type        human description, e.g. 'Verilog HDL source'
    title       document title if known
    meta        list of (label, value) facts, e.g. [('Pages', 12), ('Author', 'X')]
    summary     str: set this only if the format has a better summary than the
                automatic one (e.g. a header comment). Otherwise core builds one.
    keywords    list[str]: extra keywords to put first (part numbers, module names)
    paragraphs  list of str | {'heading': str}: the FULL text in reading order,
                one paragraph per item. Headings like {'heading': 'Page 3'}.
    functions   list of dicts: {'name','kind','line','signature','doc',
                'params': [(name, type/dir, note)], 'returns': str, 'calls': [names]}
    outline     list of str | {'heading': str}: other structure
                (modules, ports, sheets, archive entries ...) rendered as a list
    code_lang   language tag used for signature code fences ('c','verilog','vhdl'...)
    notes       list[str]: caveats ('No text layer - needs OCR', 'truncated' ...)

Extractors must never modify or execute the file, must not import heavy
modules at top level unless installed, and must finish quickly (core kills a
file after TIMEOUT seconds and falls back to the generic extractor).
"""
import re, math, collections

STOP = set("""a about above after again against all also am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further had has have having
he her here hers herself him himself his how i if in into is it its itself just me more most my myself no nor not
now of off on once only or other our ours ourselves out over own same she should so some such than that the their
theirs them themselves then there these they this those through to too under until up very was we were what when
where which while who whom why will with would you your yours yourself yourselves may must shall use used using
one two three see page pages table figure fig note notes also via per etc e g ie eg rev www http https com inc ltd
end begin if else then elsif when case others null true false return int void char unsigned signed long short
static const define include ifdef ifndef endif wire reg input output inout assign always posedge negedge module
endmodule signal std_logic std_logic_vector downto entity architecture is of port map process library ieee
all new following shown section chapter document copyright reserved rights""".split())

WORD = re.compile(r"[A-Za-z][A-Za-z0-9_\-\.]*[A-Za-z0-9]|[A-Za-z]")
PARTNO = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9][A-Za-z0-9\-_/\.]{2,}$")
SENT = re.compile(r"(?<=[\.\!\?])\s+(?=[A-Z0-9\(\"'])")


def _tokens(text):
    for m in WORD.finditer(text):
        w = m.group(0).strip('.-_')
        if len(w) < 3 and not w.isupper():
            continue
        yield w


def keywords(text, extra=(), n=15):
    """Frequency keywords; part-number-like tokens (letters+digits) weighted up."""
    cnt = collections.Counter()
    shown = {}
    for w in _tokens(text):
        lw = w.lower()
        if lw in STOP or lw.isdigit() or len(lw) > 40:
            continue
        cnt[lw] += 3 if PARTNO.match(w) else 1
        shown.setdefault(lw, w)
    out, seen = [], set()
    for k in extra:
        k = str(k).strip()
        if k and k.lower() not in seen:
            out.append(k); seen.add(k.lower())
    for lw, _ in cnt.most_common(n * 2):
        if lw not in seen:
            out.append(shown[lw]); seen.add(lw)
        if len(out) >= n:
            break
    return out[:n]


def summarize(paragraphs, max_sent=4, max_chars=700):
    """Extractive summary: top-scoring sentences (by keyword weight), in original order."""
    text_pars = [p for p in paragraphs if isinstance(p, str) and p.strip()]
    if not text_pars:
        return ''
    full = '\n'.join(text_pars)
    freq = collections.Counter(w.lower() for w in _tokens(full) if w.lower() not in STOP)
    if not freq:
        return text_pars[0][:max_chars]
    top = max(freq.values())
    sents = []
    for p in text_pars[:400]:
        for s in SENT.split(p.replace('\n', ' ')):
            s = s.strip()
            words = [w.lower() for w in _tokens(s)]
            if len(words) < 5 or len(s) > 400:
                continue
            alpha = sum(c.isalpha() for c in s) / max(1, len(s))
            if alpha < 0.6:
                continue
            score = sum(freq.get(w, 0) / top for w in words if w not in STOP) / math.sqrt(len(words))
            sents.append((score, len(sents), s))
    if not sents:
        first = text_pars[0].replace('\n', ' ')
        return first[:max_chars]
    best = sorted(sents, reverse=True)[:max_sent]
    best.sort(key=lambda x: x[1])
    out = ''
    for _, _, s in best:
        if len(out) + len(s) > max_chars and out:
            break
        out += (' ' if out else '') + s
    return out


def split_paragraphs(text):
    """Plain text -> paragraphs on blank lines; collapses intra-paragraph whitespace."""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    pars = []
    for block in re.split(r'\n\s*\n', text):
        b = block.strip()
        if b:
            pars.append(b)
    return pars


def read_text(path, limit=20_000_000):
    """Read a file as text (utf-8, falling back to cp1252/latin-1). Returns (text, truncated)."""
    with open(path, 'rb') as f:
        data = f.read(limit + 1)
    trunc = len(data) > limit
    data = data[:limit]
    for enc in ('utf-8', 'cp1252', 'latin-1'):
        try:
            return data.decode(enc), trunc
        except UnicodeDecodeError:
            continue
    return data.decode('latin-1', 'replace'), trunc


def looks_binary(path, n=8192):
    with open(path, 'rb') as f:
        chunk = f.read(n)
    if not chunk:
        return False
    if b'\x00' in chunk:
        return True
    ctrl = sum(1 for b in chunk if b < 9 or (13 < b < 32))
    return ctrl / len(chunk) > 0.10
