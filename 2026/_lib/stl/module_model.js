// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
// A module as a 3-D model from its wbs-model/1 JSON (tools/module_models.py): the front panel with the holes and
// cut-outs its drawing draws, the knobs of its controls, and the PC card (or rack chassis) behind it.
// The same code makes the STL files (tools/stl/make_stl.mjs, under node) and the site's viewer (2026/stl.html):
// three.js is passed in, so neither needs the other's way of loading it.
//
//   buildModule(THREE, model, opts) -> THREE.Group        opts: {knobs, body, holes, t, d, segments}
//   toSTL(THREE, object, name)      -> ArrayBuffer (binary STL, mm)

export const DEFAULTS = { knobs: true, body: true, holes: true, t: null, d: null, segments: 64 };

export function buildModule(THREE, model, opts = {}) {
  const o = { ...DEFAULTS, ...opts };
  const W = model.size.w, H = model.size.h;
  const T = o.t ?? model.panel.t ?? 3.2;
  const D = o.d ?? model.size.d ?? 165;
  const group = new THREE.Group();
  group.name = model.module;
  const metal = new THREE.MeshStandardMaterial({ color: 0xc9ccd1, metalness: 0.55, roughness: 0.38 });
  const black = new THREE.MeshStandardMaterial({ color: 0x1d1d1f, metalness: 0.1, roughness: 0.55 });
  const green = new THREE.MeshStandardMaterial({ color: 0x2f6b3a, metalness: 0.05, roughness: 0.7 });

  // the front panel: a plate W x H x T with the drawing's holes, face at z = 0, extruded backwards
  const shape = new THREE.Shape();
  shape.moveTo(0, 0); shape.lineTo(W, 0); shape.lineTo(W, H); shape.lineTo(0, H); shape.closePath();
  if (o.holes) {
    for (const h of model.holes) {
      const p = new THREE.Path();
      if (h.shape === 'circle') p.absarc(h.x, h.y, h.r, 0, Math.PI * 2, true);
      else {
        const x0 = h.x - h.w / 2, y0 = h.y - h.h / 2;
        p.moveTo(x0, y0); p.lineTo(x0, y0 + h.h); p.lineTo(x0 + h.w, y0 + h.h); p.lineTo(x0 + h.w, y0); p.closePath();
      }
      shape.holes.push(p);
    }
  }
  const plate = new THREE.ExtrudeGeometry(shape, { depth: T, bevelEnabled: false, curveSegments: o.segments });
  plate.translate(0, 0, -T);
  const panel = new THREE.Mesh(plate, metal);
  panel.name = 'panel';
  group.add(panel);

  // knobs: a cylinder of the drawn size on each control, standing out of the face, with its pointer
  if (o.knobs) {
    for (const k of model.knobs || []) {
      const h = Math.min(18, Math.max(9, k.r * 1.1));
      const g = new THREE.CylinderGeometry(k.r * 0.9, k.r, h, o.segments);
      g.rotateX(Math.PI / 2);
      g.translate(k.x, k.y, h / 2);
      const knob = new THREE.Mesh(g, black);
      knob.name = 'knob';
      group.add(knob);
      const pg = new THREE.BoxGeometry(Math.max(0.8, k.r * 0.12), k.r * 0.75, 0.6);
      pg.translate(k.x, k.y + k.r * 0.45, h + 0.3);
      const ptr = new THREE.Mesh(pg, metal);
      ptr.name = 'pointer';
      group.add(ptr);
    }
  }

  // behind the panel: the PC card down the middle, or a rack chassis
  if (o.body) {
    if (model.body === 'chassis') {
      const ear = Math.min(19, W * 0.04);
      const g = new THREE.BoxGeometry(W - 2 * ear, Math.max(10, H - 2), D);
      g.translate(W / 2, H / 2, -T - D / 2);
      const box = new THREE.Mesh(g, metal);
      box.name = 'chassis';
      group.add(box);
    } else {
      const cardH = Math.max(10, H - 20);
      const g = new THREE.BoxGeometry(1.6, cardH, D);
      g.translate(W / 2, H / 2, -T - D / 2);
      const card = new THREE.Mesh(g, green);
      card.name = 'card';
      group.add(card);
      // the edge connector's fingers at the back of the card
      const f = new THREE.BoxGeometry(1.8, Math.min(cardH * 0.6, 90), 8);
      f.translate(W / 2, H / 2, -T - D + 4);
      const fingers = new THREE.Mesh(f, new THREE.MeshStandardMaterial({ color: 0xc8a24a, metalness: 0.8, roughness: 0.3 }));
      fingers.name = 'connector';
      group.add(fingers);
      // the bracket holding the card to the panel
      const b = new THREE.BoxGeometry(12, cardH, 1.6);
      b.translate(W / 2 + 6.8, H / 2, -T - 0.8);
      const bracket = new THREE.Mesh(b, metal);
      bracket.name = 'bracket';
      group.add(bracket);
    }
  }
  return group;
}

export function toSTL(THREE, object, name = 'model') {
  object.updateMatrixWorld(true);
  const tris = [];
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  const n = new THREE.Vector3(), e1 = new THREE.Vector3(), e2 = new THREE.Vector3();
  object.traverse((m) => {
    if (!m.isMesh) return;
    const g = m.geometry.index ? m.geometry.toNonIndexed() : m.geometry;
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i += 3) {
      a.fromBufferAttribute(p, i).applyMatrix4(m.matrixWorld);
      b.fromBufferAttribute(p, i + 1).applyMatrix4(m.matrixWorld);
      c.fromBufferAttribute(p, i + 2).applyMatrix4(m.matrixWorld);
      n.crossVectors(e1.subVectors(b, a), e2.subVectors(c, a)).normalize();
      tris.push(n.x, n.y, n.z, a.x, a.y, a.z, b.x, b.y, b.z, c.x, c.y, c.z);
    }
  });
  const count = tris.length / 12;
  const buf = new ArrayBuffer(84 + count * 50);
  const dv = new DataView(buf);
  const head = `WBS ${name} (mm) - Ward-Beck Systems`.slice(0, 80);
  for (let i = 0; i < head.length; i++) dv.setUint8(i, head.charCodeAt(i) & 0x7f);
  dv.setUint32(80, count, true);
  let off = 84;
  for (let t = 0; t < count; t++) {
    for (let j = 0; j < 12; j++) { dv.setFloat32(off, tris[t * 12 + j], true); off += 4; }
    dv.setUint16(off, 0, true); off += 2;
  }
  return buf;
}
