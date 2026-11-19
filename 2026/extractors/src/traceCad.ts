/**
 * traceCad — CAD files made from a traced drawing's SVG (timelines/trace_drawings.py writes _traces/<sha16>.svg).
 *
 * The SVG is the data: on <svg> the sheet's facts (data-number, data-title, data-dtype, data-size, data-rotate) and its
 * viewBox (pixels of the upright sheet); <g class="cl"> the ink's centre lines as paths "cl-line", "cl-text" (lettering)
 * and "cl-tb" (title block); <rect class="block"> a functional diagram's boxes; <text class="ocr"> the words read.
 *
 *   parseTrace(svg)   → Trace
 *   toDxf(trace)      → AutoCAD DXF (R12, millimetres; layers LINE, LETTERING, TITLEBLOCK, BLOCKS, OCRTEXT)
 *   toKicadSch(trace) → KiCad 8 schematic: long straight runs as wires on the 1.27 mm grid, the rest as graphic lines,
 *                       blocks as rectangles, words as text: a sheet to redraw with symbols over
 *   toPdf(trace)      → a vector PDF of the drawing (the traced ink as filled shapes), its words as invisible text so it
 *                       can be searched and copied
 *   toPptx(trace, png) → a PowerPoint slide: the drawing, its number and title, where it came from (pptxgenjs; browser)
 *   convert(svg)      → the file a drawing's type asks for: mechanical (-03-) DXF, electrical (-01-, -02-, -09-) KiCad
 *
 * Built twice (npm run build:cad): _catalog/trace_cad.js for the browser (window.TraceCad) and timelines/trace_cad.cjs,
 * the command line (traceCadCli.ts).
 */

export type Pt = [number, number];
export type Cls = 'line' | 'text' | 'tb';
export interface Word { x0: number; y0: number; x1: number; y1: number; text: string }
export interface Trace {
  W: number; H: number; number: string; title: string; dtype: string; size: string; rotate: number;
  lines: { cls: Cls; pts: Pt[] }[];
  outlines: { cls: Cls; d: string }[];   // the traced ink as filled outlines (what the overlay shows)
  blocks: [number, number, number, number][];
  words: Word[];
}
export interface CadFile { ext: 'dxf' | 'kicad_sch'; what: string; mime: string; text: string }

export const ELECTRICAL = new Set(['01', '02', '09']);
export const MECHANICAL = new Set(['03']);
/** The long side of Ward-Beck's sheet sizes, in mm (A 11in, B 17, C 22, D 34). */
const SHEET_MM: Record<string, number> = { A: 279.4, B: 431.8, C: 558.8, D: 863.6 };

const unescape = (s: string) => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
const attr = (tag: string, name: string) => { const m = tag.match(new RegExp(`\\s${name}="([^"]*)"`)); return m ? unescape(m[1]) : ''; };

export function parseTrace(svg: string): Trace {
  const root = (svg.match(/<svg\b[^>]*>/) || [''])[0];
  const vb = attr(root, 'viewBox').split(/\s+/).map(Number);
  const t: Trace = {
    W: vb[2] || 1, H: vb[3] || 1, number: attr(root, 'data-number'), title: attr(root, 'data-title'),
    dtype: attr(root, 'data-dtype'), size: attr(root, 'data-size'), rotate: +attr(root, 'data-rotate') || 0,
    lines: [], outlines: [], blocks: [], words: [],
  };
  for (const m of svg.matchAll(/<path class="(line|text|tb)" d="([^"]*)"/g)) t.outlines.push({ cls: m[1] as Cls, d: m[2] });
  for (const m of svg.matchAll(/<path class="cl-(line|text|tb)" d="([^"]*)"/g)) {
    for (const part of m[2].split('M')) {
      const pts = part.split('L').map(p => p.trim().split(/\s+/).map(Number) as Pt).filter(p => p.length === 2 && !isNaN(p[0]));
      if (pts.length >= 2) t.lines.push({ cls: m[1] as Cls, pts });
    }
  }
  for (const m of svg.matchAll(/<rect class="block"[^>]*>/g)) {
    const x = +attr(m[0], 'x'), y = +attr(m[0], 'y');
    t.blocks.push([x, y, x + +attr(m[0], 'width'), y + +attr(m[0], 'height')]);
  }
  for (const m of svg.matchAll(/<text class="ocr"([^>]*)>([^<]*)<\/text>/g)) {
    const x = +attr(m[0], 'x'), y = +attr(m[0], 'y'), fs = +attr(m[0], 'font-size'), w = +attr(m[0], 'textLength');
    t.words.push({ x0: x, y0: y - fs / .9, x1: x + w, y1: y, text: unescape(m[2]) });
  }
  return t;
}

const mmPerPx = (t: Trace) => (SHEET_MM[t.size] || SHEET_MM.B) / Math.max(t.W, t.H);
const fileName = (t: Trace) => (t.number || 'drawing').replace(/[^\w .-]+/g, '_');

/** An outline path (M … L … Q … Z, as the tracer writes it) as closed rings of points; curves by their end points. */
function outlineRings(d: string): Pt[][] {
  const rings: Pt[][] = [], tok = d.match(/[MLQZ]|-?\d*\.?\d+/g) || [];
  let ring: Pt[] = [], cmd = '', i = 0;
  while (i < tok.length) {
    if (/[MLQZ]/.test(tok[i])) cmd = tok[i++];
    if (cmd === 'M') { if (ring.length > 2) rings.push(ring); ring = [[+tok[i], +tok[i + 1]]]; i += 2; cmd = 'L'; }
    else if (cmd === 'L') { ring.push([+tok[i], +tok[i + 1]]); i += 2; }
    else if (cmd === 'Q') { ring.push([+tok[i + 2], +tok[i + 3]]); i += 4; }
    else if (cmd === 'Z') { if (ring.length > 2) rings.push(ring); ring = []; cmd = ''; }
    else i++;
  }
  if (ring.length > 2) rings.push(ring);
  return rings;
}

/** AutoCAD R12 DXF: plain ASCII, read by AutoCAD, DraftSight, LibreCAD, FreeCAD, QCAD. Y runs up, so the sheet is flipped. */
export function toDxf(t: Trace): string {
  const k = mmPerPx(t), r2 = (v: number) => String(+v.toFixed(2));   // 0.01 mm is plenty for a traced scan: small files
  const X = (x: number) => r2(x * k), Y = (y: number) => r2((t.H - y) * k);
  const out: string[] = [];
  const g = (code: number, v: string | number) => out.push(String(code), String(v));
  const LAYERS: [string, number][] = [['LINE', 7], ['LETTERING', 3], ['TITLEBLOCK', 5], ['BLOCKS', 2], ['OCRTEXT', 1]];
  const layerOf: Record<Cls, string> = { line: 'LINE', text: 'LETTERING', tb: 'TITLEBLOCK' };
  g(0, 'SECTION'); g(2, 'HEADER');
  g(9, '$ACADVER'); g(1, 'AC1009');
  g(9, '$INSUNITS'); g(70, 4);   // millimetres
  g(9, '$EXTMIN'); g(10, 0); g(20, -20);
  g(9, '$EXTMAX'); g(10, X(t.W)); g(20, Y(0));
  g(0, 'ENDSEC');
  g(0, 'SECTION'); g(2, 'TABLES');
  g(0, 'TABLE'); g(2, 'LAYER'); g(70, LAYERS.length);
  for (const [name, colour] of LAYERS) { g(0, 'LAYER'); g(2, name); g(70, 0); g(62, colour); g(6, 'CONTINUOUS'); }
  g(0, 'ENDTAB'); g(0, 'ENDSEC');
  g(0, 'SECTION'); g(2, 'ENTITIES');
  const poly = (layer: string, pts: Pt[], closed = false) => {
    if (pts.length === 2 && !closed) {   // a straight run: one LINE, a third the size of a two-vertex polyline
      g(0, 'LINE'); g(8, layer); g(10, X(pts[0][0])); g(20, Y(pts[0][1])); g(11, X(pts[1][0])); g(21, Y(pts[1][1]));
      return;
    }
    g(0, 'POLYLINE'); g(8, layer); g(66, 1); g(70, closed ? 1 : 0);
    for (const [x, y] of pts) { g(0, 'VERTEX'); g(10, X(x)); g(20, Y(y)); }   // a vertex draws on its polyline's layer
    g(0, 'SEQEND'); g(8, layer);
  };
  const text = (layer: string, x: string, y: string, h: number, s: string) => {
    g(0, 'TEXT'); g(8, layer); g(10, x); g(20, y); g(40, h.toFixed(2)); g(1, s.replace(/[\r\n]+/g, ' '));
  };
  for (const l of t.lines) poly(layerOf[l.cls], l.pts);
  if (!t.lines.length) for (const o of t.outlines) for (const ring of outlineRings(o.d)) poly(layerOf[o.cls], ring, true);   // no centre lines: the ink's outlines
  for (const [x0, y0, x1, y1] of t.blocks) poly('BLOCKS', [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], true);
  for (const w of t.words) text('OCRTEXT', X(w.x0), Y(w.y1), Math.max(.5, (w.y1 - w.y0) * k * .8), w.text);
  text('TITLEBLOCK', '0', '-8', 3.5, `${t.number} ${t.title}`.trim());
  text('TITLEBLOCK', '0', '-13', 2, 'Traced from the Ward-Beck archive scan (WBSps.ca)');
  g(0, 'ENDSEC'); g(0, 'EOF');
  return out.join('\n') + '\n';
}

const uuid = () => (globalThis.crypto && 'randomUUID' in globalThis.crypto) ? globalThis.crypto.randomUUID()
  : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => { const r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 3) | 8).toString(16); });
const q = (s: string) => '"' + s.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';

/** KiCad 8 schematic (opens in KiCad 8 and 9). */
export function toKicadSch(t: Trace): string {
  const k = mmPerPx(t), G = 1.27, snap = (v: number) => Math.round(v / G) * G;
  const xy = (x: number, y: number): Pt => [+(10 + x * k).toFixed(3), +(10 + y * k).toFixed(3)];
  const pw = +(t.W * k + 20).toFixed(2), ph = +(t.H * k + 30).toFixed(2);
  const out = [
    `(kicad_sch (version 20231120) (generator "wbsps_tracer") (generator_version "1") (uuid "${uuid()}")`,
    `  (paper "User" ${pw} ${ph})`,
    `  (title_block (title ${q(t.title || t.number)}) (company "Ward-Beck Systems") (comment 1 ${q('Drawing ' + t.number)})` +
    ` (comment 2 "Traced from the archive scan: redraw with symbols over it"))`,
    '  (lib_symbols)',
  ];
  const words = t.words.length > 0;   // the words go in as text: the traced lettering is not needed as well
  for (const l of t.lines) {
    if (words && l.cls === 'text') continue;
    const p = l.pts.map(([x, y]) => xy(x, y));
    if (l.cls === 'line' && p.length === 2) {
      let [[x0, y0], [x1, y1]] = p;
      const flat = Math.abs(y0 - y1) < .5, tall = Math.abs(x0 - x1) < .5;
      if ((flat || tall) && Math.hypot(x1 - x0, y1 - y0) >= 5 * G) {   // a wire
        if (tall) { x0 = x1 = snap((x0 + x1) / 2); y0 = snap(y0); y1 = snap(y1); }
        else { y0 = y1 = snap((y0 + y1) / 2); x0 = snap(x0); x1 = snap(x1); }
        out.push(`  (wire (pts (xy ${x0.toFixed(2)} ${y0.toFixed(2)}) (xy ${x1.toFixed(2)} ${y1.toFixed(2)})) (stroke (width 0) (type default)) (uuid "${uuid()}"))`);
        continue;
      }
    }
    out.push(`  (polyline (pts ${p.map(([x, y]) => `(xy ${x} ${y})`).join(' ')}) (stroke (width ${l.cls === 'line' ? 0.15 : 0.1}) (type default)) (uuid "${uuid()}"))`);
  }
  for (const [x0, y0, x1, y1] of t.blocks) {   // a functional diagram's blocks, whole
    const [a, b] = xy(x0, y0), [c, d] = xy(x1, y1);
    out.push(`  (rectangle (start ${a} ${b}) (end ${c} ${d}) (stroke (width 0.25) (type default)) (fill (type none)) (uuid "${uuid()}"))`);
  }
  for (const w of t.words) {
    const [a, b] = xy(w.x0, w.y1), sz = Math.max(.6, +((w.y1 - w.y0) * k * .8).toFixed(2));
    out.push(`  (text ${q(w.text)} (exclude_from_sim no) (at ${a} ${b} 0) (effects (font (size ${sz} ${sz})) (justify left bottom)) (uuid "${uuid()}"))`);
  }
  out.push(`  (text ${q(`${t.number} ${t.title}`.trim())} (exclude_from_sim no) (at 10 ${+(t.H * k + 20).toFixed(2)} 0)` +
           ` (effects (font (size 2.54 2.54)) (justify left bottom)) (uuid "${uuid()}"))`);
  out.push('  (sheet_instances (path "/" (page "1")))', ')');
  return out.join('\n') + '\n';
}

/** A one-page vector PDF (PDF 1.4, no compression): the outlines filled in ink, the OCR words as invisible text. */
export function toPdf(t: Trace): Uint8Array {
  const k = mmPerPx(t) * 72 / 25.4, M = 24;   // points per pixel, margin
  const PW = +(t.W * k + 2 * M).toFixed(2), PH = +(t.H * k + 2 * M + 22).toFixed(2);
  const X = (x: number) => (M + x * k).toFixed(2), Y = (y: number) => (PH - M - y * k).toFixed(2);
  const ops: string[] = ['0 g'];
  for (const o of t.outlines) {   // M x y L x y Q cx cy x y Z  →  m l c h, then fill (non-zero, holes run the other way)
    const tok = o.d.match(/[MLQZ]|-?\d*\.?\d+/g) || [];
    let i = 0, cx = 0, cy = 0, cmd = '';
    const num = () => +tok[i++];
    while (i < tok.length) {
      if (/[MLQZ]/.test(tok[i])) cmd = tok[i++];
      if (cmd === 'M') { cx = num(); cy = num(); ops.push(`${X(cx)} ${Y(cy)} m`); cmd = 'L'; }
      else if (cmd === 'L') { cx = num(); cy = num(); ops.push(`${X(cx)} ${Y(cy)} l`); }
      else if (cmd === 'Q') {
        const qx = num(), qy = num(), x = num(), y = num();
        ops.push(`${X(cx + 2 / 3 * (qx - cx))} ${Y(cy + 2 / 3 * (qy - cy))} ${X(x + 2 / 3 * (qx - x))} ${Y(y + 2 / 3 * (qy - y))} ${X(x)} ${Y(y)} c`);
        cx = x; cy = y;
      } else if (cmd === 'Z') { ops.push('h'); cmd = ''; }
      else i++;
    }
    ops.push('f');
  }
  const pdfStr = (s: string) => '(' + s.replace(/[^\x20-\x7e]/g, '?').replace(/([\\()])/g, '\\$1') + ')';
  ops.push('BT 3 Tr');   // the words, invisible: found by search, copied with the selection
  for (const w of t.words) {
    const size = Math.max(2, (w.y1 - w.y0) * k * .85);
    ops.push(`/F1 ${size.toFixed(2)} Tf 1 0 0 1 ${X(w.x0)} ${Y(w.y1)} Tm ${pdfStr(w.text)} Tj`);
  }
  ops.push(`0 Tr /F1 9 Tf 1 0 0 1 ${M} ${(M / 2 + 4).toFixed(2)} Tm ${pdfStr(`${t.number} ${t.title} - traced from the Ward-Beck archive scan (WBSps.ca)`.trim())} Tj ET`);
  const content = ops.join('\n');
  const objs = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PW} ${PH}] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>`,
    `<< /Length ${content.length} >>\nstream\n${content}\nendstream`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Title ${pdfStr(`${t.number} ${t.title}`.trim())} /Producer (WBSps drawing tracer) >>`,
  ];
  let out = '%PDF-1.4\n';
  const at: number[] = [];
  objs.forEach((o, n) => { at.push(out.length); out += `${n + 1} 0 obj\n${o}\nendobj\n`; });
  const xref = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n` + at.map(a => String(a).padStart(10, '0') + ' 00000 n \n').join('');
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R /Info 6 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return new TextEncoder().encode(out);   // all ASCII: byte offsets are character offsets
}

/** A PowerPoint slide with the drawing (a PNG made from the trace), its number, title and source. */
export async function toPptx(t: Trace, png: string, source = ''): Promise<Blob> {
  const { default: PptxGenJS } = await import('pptxgenjs');
  const pptx = new PptxGenJS();
  pptx.layout = 'LAYOUT_WIDE';   // 13.33 × 7.5 in
  pptx.title = `${t.number} ${t.title}`.trim();
  const s = pptx.addSlide();
  s.background = { color: 'FBFAF4' };
  s.addText(`${t.number}  ${t.title}`.trim(), { x: .4, y: .2, w: 12.5, h: .5, fontFace: 'Courier New', fontSize: 20, bold: true, color: '1F1E1C' });
  const boxW = 12.5, boxH = 6.1, r = t.W / t.H;
  const w = Math.min(boxW, boxH * r), h = w / r;
  s.addImage({ data: png, x: .4 + (boxW - w) / 2, y: .8 + (boxH - h) / 2, w, h });
  s.addText('Traced from the Ward-Beck Systems archive · WBSps.ca' + (source ? ' · ' + source : ''),
    { x: .4, y: 7.0, w: 12.5, h: .3, fontFace: 'Courier New', fontSize: 9, color: '6D6A63' });
  if (t.words.length) s.addNotes('Words read on the drawing: ' + t.words.map(w => w.text).join(' · '));
  return await pptx.write({ outputType: 'blob' }) as Blob;
}

/** The CAD file this drawing's type asks for, or null (layouts, artwork: their boards are KiCad already). */
export function convert(svg: string): (CadFile & { name: string }) | null {
  const t = parseTrace(svg);
  if (!t.lines.length) return null;
  if (MECHANICAL.has(t.dtype)) return { ext: 'dxf', what: 'DXF (AutoCAD)', mime: 'application/dxf', text: toDxf(t), name: fileName(t) + '.dxf' };
  if (ELECTRICAL.has(t.dtype)) return { ext: 'kicad_sch', what: 'KiCad schematic', mime: 'text/plain', text: toKicadSch(t), name: fileName(t) + '.kicad_sch' };
  return null;
}
