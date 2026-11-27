// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
// <module>/MECHANICAL/<Mxxx>.stl from <Mxxx>.model.json (tools/module_models.py), for every module repo clone,
// with the same builder the site's viewer uses (2026/_lib/stl/module_model.js).
//
//   cd tools/stl && npm install && node make_stl.mjs [Mxxx ...]
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as THREE from 'three';
import { buildModule, toSTL } from '../../2026/_lib/stl/module_model.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..', '..');
const clones = path.join(root, 'WBSps.ca', 'Github.WardBeckSystems');
const want = new Set(process.argv.slice(2));
let made = 0, tris = 0;
for (const repo of fs.readdirSync(clones).filter((d) => d.startsWith('MODULES.')).sort()) {
  const mech = path.join(clones, repo, 'MECHANICAL');
  if (!fs.existsSync(mech)) continue;
  for (const f of fs.readdirSync(mech).filter((f) => f.endsWith('.model.json'))) {
    const model = JSON.parse(fs.readFileSync(path.join(mech, f), 'utf8'));
    if (want.size && !want.has(model.module)) continue;
    const buf = toSTL(THREE, buildModule(THREE, model), model.module);
    fs.writeFileSync(path.join(mech, `${model.module}.stl`), Buffer.from(buf));
    made++; tris += new DataView(buf).getUint32(80, true);
  }
}
console.log(`${made} STL files, ${tris.toLocaleString()} triangles`);
