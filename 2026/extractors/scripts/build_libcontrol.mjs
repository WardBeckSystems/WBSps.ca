// OPEN-AIR's control library (2026/_lib/OPEN-AIR/libControl, from github.com/LikeDotAudio/OPEN-AIR FrontEnd/libControl)
// built for the archive's pages: every component in OPEN-AIR's own load order (load_order.txt, from its index.html),
// JSX compiled ahead of time (no Babel in the browser), in one script.
//
// Out: 2026/_catalog/libcontrol/libcontrol.js   the components, on window (Knob, LTPFader, Fader, OcaWinkButton,
//                                              WinkButtonToggler, ButtonToggler, OcaTrapezoidButton, NeedleMeter …)
//      2026/_catalog/libcontrol/libcontrol.css  their stylesheets
//      2026/_catalog/libcontrol/react.js, react-dom.js   React 18.3.1 (production), which they run on
//      2026/_catalog/libcontrol/Panels/wasm/pkg/oa_panels_bg.wasm   the procedural panel / screw engine
// usage: node scripts/build_libcontrol.mjs   (npm run build:libcontrol)
import { transformSync } from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const LIB = path.resolve(HERE, '..', '..', '_lib', 'OPEN-AIR');
const OUT = path.resolve(HERE, '..', '..', '_catalog', 'libcontrol');
const order = fs.readFileSync(path.join(LIB, 'load_order.txt'), 'utf8').split('\n').map(s => s.trim()).filter(Boolean);
const classic = new Set(fs.readFileSync(path.join(LIB, 'classic.txt'), 'utf8').split('\n').map(s => s.trim()).filter(Boolean));

fs.mkdirSync(path.join(OUT, 'Panels', 'wasm', 'pkg'), { recursive: true });
const parts = [
  '/* OPEN-AIR libControl for the WBSps.ca archive: https://github.com/LikeDotAudio/OPEN-AIR (FrontEnd/libControl). Built by build_libcontrol.mjs. */',
  // where this script was loaded from, so the wasm panel engine is found beside it
  "window.OA_LIB_BASE = (document.currentScript && document.currentScript.src || '').replace(/libcontrol\\.js(\\?.*)?$/, '');",
];
let n = 0;
for (const rel of order) {
  const file = path.join(LIB, rel);
  if (!fs.existsSync(file)) { console.warn('missing', rel); continue; }
  let src = fs.readFileSync(file, 'utf8');
  if (!classic.has(rel)) {
    src = transformSync(src, { loader: rel.endsWith('.jsx') ? 'jsx' : 'js', jsx: 'transform', jsxFactory: 'React.createElement',
                               jsxFragment: 'React.Fragment', target: 'es2020', sourcefile: rel }).code;
  }
  src = src.replace(/"\/libControl\/Panels\/wasm\/pkg\/oa_panels_bg\.wasm\?v=\d+"/, "(window.OA_LIB_BASE + 'Panels/wasm/pkg/oa_panels_bg.wasm')");
  if (classic.has(rel)) {   // OPEN-AIR's classic scripts (the wasm engine and its loader): as they are, one scope for both
    parts.push(`/* ---- ${rel} ---- */\n${src}\n;`);
    n++;
    continue;
  }
  // each file as OPEN-AIR runs it: its own script, sharing the page's globals. A failing one does not stop the rest.
  parts.push(`/* ---- ${rel} ---- */\ntry { (0, eval)(${JSON.stringify(src)}); } catch (e) { console.warn('libControl: ${rel}', e); }`);
  n++;
}
fs.writeFileSync(path.join(OUT, 'libcontrol.js'), parts.join('\n') + '\n');
const css = [];
for (const walk of [path.join(LIB, 'libControl')]) {
  const stack = [walk];
  while (stack.length) {
    const d = stack.pop();
    for (const f of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, f.name);
      if (f.isDirectory()) stack.push(p);
      else if (f.name.endsWith('.css')) css.push(`/* ${path.relative(LIB, p)} */\n` + fs.readFileSync(p, 'utf8'));
    }
  }
}
fs.writeFileSync(path.join(OUT, 'libcontrol.css'), css.join('\n'));
fs.copyFileSync(path.join(LIB, 'libControl', 'Panels', 'wasm', 'pkg', 'oa_panels_bg.wasm'), path.join(OUT, 'Panels', 'wasm', 'pkg', 'oa_panels_bg.wasm'));
fs.copyFileSync(path.join(LIB, 'wbs_presets.json'), path.join(OUT, 'wbs_presets.json'));   // the WBS looks, from OPEN-AIR's samples
const NM = path.resolve(HERE, '..', 'node_modules');
fs.copyFileSync(path.join(NM, 'react', 'umd', 'react.production.min.js'), path.join(OUT, 'react.js'));
fs.copyFileSync(path.join(NM, 'react-dom', 'umd', 'react-dom.production.min.js'), path.join(OUT, 'react-dom.js'));
console.log(`libControl: ${n} components -> ${path.relative(process.cwd(), OUT)}/libcontrol.js (${(fs.statSync(path.join(OUT, 'libcontrol.js')).size / 1e6).toFixed(2)} MB)`);
