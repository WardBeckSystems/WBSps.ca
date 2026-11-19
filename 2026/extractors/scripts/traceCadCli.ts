/**
 * The traced drawings' CAD files from the command line (built to timelines/trace_cad.cjs by npm run build:cad).
 *
 * usage: node trace_cad.cjs <traced .svg or folder of them> [--out DIR] [--dxf] [--kicad]
 *        node trace_cad.cjs --pairs PAIRS.json --dxf      [[svg, out.dxf], …]: each trace to the path given (made again
 *                                                          only when the trace is newer)
 *   by default each drawing gets the file its type asks for (mechanical → DXF, electrical → KiCad schematic);
 *   --dxf / --kicad make that one for every drawing. With the ODA File Converter installed, each DXF also becomes a DWG.
 */
import * as fs from 'node:fs';
import * as path from 'node:path';
import { execFileSync } from 'node:child_process';
import { convert, parseTrace, toDxf, toKicadSch } from '../src/traceCad';

const args = process.argv.slice(2);
const flag = (f: string) => args.includes(f);
const outAt = args.indexOf('--out');
const out = outAt >= 0 ? args[outAt + 1] : '';
const pairsAt = args.indexOf('--pairs');
const src = args.find((a, i) => !a.startsWith('--') && !(outAt >= 0 && i === outAt + 1) && !(pairsAt >= 0 && i === pairsAt + 1));
if (pairsAt >= 0) {   // each trace to its own place (trace_drawings.py: beside the drawing it was traced from)
  const pairs: [string, string][] = JSON.parse(fs.readFileSync(args[pairsAt + 1], 'utf8'));
  let made = 0;
  for (const [svgPath, outPath] of pairs) {
    if (!fs.existsSync(svgPath)) continue;
    if (fs.existsSync(outPath) && fs.statSync(outPath).mtimeMs >= fs.statSync(svgPath).mtimeMs) continue;
    const t = parseTrace(fs.readFileSync(svgPath, 'utf8'));
    if (!t.lines.length && !t.outlines.length) continue;
    fs.writeFileSync(outPath, outPath.endsWith('.kicad_sch') ? toKicadSch(t) : toDxf(t));
    made++;
  }
  console.log(`${made} CAD files written beside their drawings (${pairs.length} traced)`);
  process.exit(0);
}
if (!src) { console.error('usage: node trace_cad.cjs <traced .svg | folder> [--out DIR] [--dxf] [--kicad]'); process.exit(2); }

const files = fs.statSync(src).isDirectory() ? fs.readdirSync(src).filter(f => f.endsWith('.svg')).map(f => path.join(src, f)) : [src];
const oda = (() => { try { return execFileSync('which', ['ODAFileConverter']).toString().trim(); } catch { return ''; } })();
let n = 0;
for (const f of files) {
  const svg = fs.readFileSync(f, 'utf8');
  const dir = out || path.dirname(f), base = path.basename(f, '.svg');
  const made: [string, string][] = [];
  if (flag('--dxf') || flag('--kicad')) {
    const t = parseTrace(svg);
    if (!t.lines.length) continue;
    if (flag('--dxf')) made.push([base + '.dxf', toDxf(t)]);
    if (flag('--kicad')) made.push([base + '.kicad_sch', toKicadSch(t)]);
  } else {
    const c = convert(svg);
    if (c) made.push([base + '.' + c.ext, c.text]);
  }
  fs.mkdirSync(dir, { recursive: true });
  for (const [name, text] of made) {
    fs.writeFileSync(path.join(dir, name), text);
    n++;
    if (oda && name.endsWith('.dxf')) {   // the ODA File Converter works folder to folder
      const a = fs.mkdtempSync(path.join(dir, '.dxf-')), b = fs.mkdtempSync(path.join(dir, '.dwg-'));
      fs.copyFileSync(path.join(dir, name), path.join(a, name));
      execFileSync(oda, [a, b, 'ACAD2018', 'DWG', '0', '1']);
      for (const d of fs.readdirSync(b)) if (d.endsWith('.dwg')) fs.renameSync(path.join(b, d), path.join(dir, d));
      fs.rmSync(a, { recursive: true }); fs.rmSync(b, { recursive: true });
    }
  }
}
console.log(`${n} CAD files from ${files.length} traced drawings${oda ? ' (and DWGs)' : ''}`);
