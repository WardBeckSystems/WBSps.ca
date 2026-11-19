import ImageTracer from 'imagetracerjs';
import { FileItem } from './types';
import { itemUrl } from './archive';
import { formatBytes } from './tree';
import { runOCR } from './ocr';
import { analyzeImage } from './imageAnalyzer';

export const KNOBS_HIGH_DETAIL_PRESET = {
  ltres: 0.1,
  qtres: 0.1,
  pathomit: 2,
  rightangleenhance: true,
  colorsampling: 2,
  numberofcolors: 48,
  mincolorratio: 0.001,
  colorquantcycles: 4,
  blurradius: 0,
  blurdelta: 10
};

// Line art: Ward-Beck drawings are black ink on white. Two fixed colours, straight lines kept straight, specks dropped.
export const DRAWING_LINE_ART_PRESET = {
  ltres: 1, qtres: 1, pathomit: 12, rightangleenhance: true, colorsampling: 0, numberofcolors: 2,
  pal: [{ r: 0, g: 0, b: 0, a: 255 }, { r: 255, g: 255, b: 255, a: 255 }], mincolorratio: 0, colorquantcycles: 1,
  blurradius: 0, blurdelta: 20, linefilter: true, strokewidth: 1, roundcoords: 1,
};
// Component layouts and board artwork: finer outlines (pads, footprints) are worth keeping.
export const DRAWING_LAYOUT_PRESET = { ...DRAWING_LINE_ART_PRESET, ltres: 0.5, qtres: 0.5, pathomit: 6 };

/** A drawing's training record (timelines/make_training.py via /api/training): type, rotation, text and title-block boxes. */
interface TrainingRecord {
  path: string; number: string; dtype: string; type: string; model: string; title: string; rotate: number;
  text: [number, number, number, number, string][]; title_block: [number, number, number, number] | null;
  target: { board: string; kicad_pcb: string; top: string; bottom: string }[] | null;
}

async function trainingFor(fileItem: FileItem): Promise<TrainingRecord | null> {
  if (!fileItem.relativePath.startsWith('2026/')) return null;
  try {
    const r = await fetch('/api/training?path=' + encodeURIComponent(fileItem.relativePath.slice(5)));
    return r.ok ? await r.json() : null;
  } catch { return null; }
}

const shardOf = (key: string) => {   // FNV-1a over UTF-8, low byte, as in timelines/make_drive_links.py
  let h = 0x811c9dc5;
  for (const b of new TextEncoder().encode(key)) { h ^= b; h = Math.imul(h, 0x01000193) >>> 0; }
  return (h & 0xff).toString(16).padStart(2, '0');
};

/** The archive tracer's SVG for a filed drawing (timelines/trace_drawings.py): upright, so `rotate` (degrees
 *  counter-clockwise) says how to turn it back onto the scan as it lies. */
export async function archiveTrace(fileItem: FileItem): Promise<{ svg: string; rotate: number; made: string } | null> {
  if (!fileItem.relativePath.startsWith('2026/')) return null;
  const rel = fileItem.relativePath.slice(5);
  try {
    const shard = await (await fetch(`/archive/_catalog/traces/${shardOf(rel)}.json`)).json();
    const t = shard[rel];
    if (!t) return null;
    const r = await fetch(`/archive/_traces/${t[0]}.svg`);
    if (!r.ok) return null;
    const rec = await trainingFor(fileItem);
    return { svg: await r.text(), rotate: rec?.rotate || 0, made: t[1] };
  } catch { return null; }
}

/** Upright, lettering and title block whited out, flattened to ink on paper: what the tracer should see of a drawing. */
async function prepareDrawing(url: string, t: TrainingRecord): Promise<{ data: ImageData; masked: number }> {
  const img = await new Promise<HTMLImageElement>((ok, bad) => { const i = new Image(); i.onload = () => ok(i); i.onerror = bad; i.src = url; });
  const side = t.rotate === 90 || t.rotate === 270, w = img.naturalWidth, h = img.naturalHeight;
  const k = Math.min(1, 2400 / Math.max(w, h));
  const cv = document.createElement('canvas');
  cv.width = Math.round((side ? h : w) * k); cv.height = Math.round((side ? w : h) * k);
  const g = cv.getContext('2d', { willReadFrequently: true })!;
  g.fillStyle = '#fff'; g.fillRect(0, 0, cv.width, cv.height);
  g.translate(cv.width / 2, cv.height / 2);
  g.rotate(-t.rotate * Math.PI / 180);   // the record's turn is counter-clockwise; the canvas turns clockwise
  g.drawImage(img, -w * k / 2, -h * k / 2, w * k, h * k);
  g.setTransform(1, 0, 0, 1, 0, 0);
  g.fillStyle = '#fff';
  const pad = 2;
  for (const [x0, y0, x1, y1] of t.text) g.fillRect(x0 * cv.width - pad, y0 * cv.height - pad, (x1 - x0) * cv.width + 2 * pad, (y1 - y0) * cv.height + 2 * pad);
  if (t.title_block) { const [x0, y0, x1, y1] = t.title_block; g.fillRect(x0 * cv.width, y0 * cv.height, (x1 - x0) * cv.width, (y1 - y0) * cv.height); }
  const data = g.getImageData(0, 0, cv.width, cv.height), p = data.data;
  let sum = 0;
  for (let i = 0; i < p.length; i += 4) sum += 0.299 * p[i] + 0.587 * p[i + 1] + 0.114 * p[i + 2];
  const cut = sum / (p.length / 4) - 40;   // ink is well below the paper's average
  for (let i = 0; i < p.length; i += 4) {
    const v = 0.299 * p[i] + 0.587 * p[i + 1] + 0.114 * p[i + 2] < cut ? 0 : 255;
    p[i] = p[i + 1] = p[i + 2] = v; p[i + 3] = 255;
  }
  // the scanner's dark edges (a lid shadow, the bed's border) are not part of the drawing: clear rows and columns of
  // mostly-black from each side inwards
  const W = cv.width, H = cv.height, dark = (x: number, y: number) => p[(y * W + x) * 4] === 0;
  const rowDark = (y: number) => { let n = 0; for (let x = 0; x < W; x += 2) n += +dark(x, y); return n / (W / 2) > .5; };
  const colDark = (x: number) => { let n = 0; for (let y = 0; y < H; y += 2) n += +dark(x, y); return n / (H / 2) > .5; };
  const clearRow = (y: number) => { for (let x = 0; x < W; x++) p.fill(255, (y * W + x) * 4, (y * W + x) * 4 + 3); };
  const clearCol = (x: number) => { for (let y = 0; y < H; y++) p.fill(255, (y * W + x) * 4, (y * W + x) * 4 + 3); };
  for (let y = 0; y < H / 4 && rowDark(y); y++) clearRow(y);
  for (let y = H - 1; y > H * 3 / 4 && rowDark(y); y--) clearRow(y);
  for (let x = 0; x < W / 4 && colDark(x); x++) clearCol(x);
  for (let x = W - 1; x > W * 3 / 4 && colDark(x); x--) clearCol(x);
  return { data, masked: t.text.length + (t.title_block ? 1 : 0) };
}

export async function convertImageToSVG(fileItem: FileItem, container: HTMLElement, customPreset?: any) {
  // an archive drawing: trace it the way the training set says (upright, lettering out, settings for its type)
  const t = customPreset ? null : await trainingFor(fileItem);
  if (t) {
    container.innerHTML = `<div class="inspector-detail"><h3>📐 Tracing drawing ${t.number} (${t.type || 'drawing'}) with the archive's training…</h3></div>`;
    try {
      const { data, masked } = await prepareDrawing(itemUrl(fileItem), t);
      const preset = t.dtype === '06' || t.dtype === '07' ? DRAWING_LAYOUT_PRESET : DRAWING_LINE_ART_PRESET;
      const svg = (ImageTracer as any).imagedataToSVG(data, preset);
      renderSVGDataUI(container, fileItem, svg, `📐 Trained drawing tracer · ${t.type || 'drawing'} · turned ${t.rotate}° · ${masked} text areas masked`);
      if (t.target && t.target.length) {
        const tg = t.target[0];
        container.insertAdjacentHTML('afterbegin', `<div class="inspector-detail"><b>Target:</b> Ward-Beck's own board file for ${escapeHTML(tg.board)} —
          <a href="/archive/${tg.top.split('/').map(encodeURIComponent).join('/')}" target="_blank">top render</a> ·
          <a href="/archive/${tg.kicad_pcb.split('/').map(encodeURIComponent).join('/')}" target="_blank">KiCad board</a></div>`);
      }
      return;
    } catch (err) {
      console.warn('trained tracing failed, using the general tracer', err);
    }
  }
  container.innerHTML = `
    <div class="inspector-detail">
      <h3>📐 High-Detail Vectorizing Image & Knob Features to SVG...</h3>
      <div class="empty-state">Tracing fine control knobs, dials, sliders, text labels & vector paths...</div>
    </div>
  `;

  const url = itemUrl(fileItem);
  const preset = customPreset || KNOBS_HIGH_DETAIL_PRESET;

  ImageTracer.imageToSVG(
    url,
    (svgString: string) => {
      URL.revokeObjectURL(url);
      renderSVGDataUI(container, fileItem, svgString, '🎛️ High-Detail Hardware Knob & Vector Tracer Engine');
    },
    preset
  );
}

function parseSVGData(svgString: string, originalSize: number) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(svgString, 'image/svg+xml');
  const svgEl = doc.querySelector('svg');

  const width = svgEl?.getAttribute('width') || (svgEl?.viewBox?.baseVal?.width ? `${svgEl.viewBox.baseVal.width}px` : 'Auto');
  const height = svgEl?.getAttribute('height') || (svgEl?.viewBox?.baseVal?.height ? `${svgEl.viewBox.baseVal.height}px` : 'Auto');
  const viewBox = svgEl?.getAttribute('viewBox') || '0 0 width height';

  const paths = doc.querySelectorAll('path');
  const polygons = doc.querySelectorAll('polygon');
  const rects = doc.querySelectorAll('rect');
  const circles = doc.querySelectorAll('circle, ellipse');
  const groups = doc.querySelectorAll('g');
  const allElements = doc.querySelectorAll('*');

  // Extract color palette
  const colorMap = new Set<string>();
  allElements.forEach(el => {
    const fill = el.getAttribute('fill');
    const stroke = el.getAttribute('stroke');
    if (fill && fill !== 'none' && fill !== 'transparent' && !fill.startsWith('url')) {
      colorMap.add(fill);
    }
    if (stroke && stroke !== 'none' && stroke !== 'transparent' && !stroke.startsWith('url')) {
      colorMap.add(stroke);
    }
  });

  const svgSizeBytes = new Blob([svgString]).size;
  const sizeRatioPercent = originalSize > 0 ? ((svgSizeBytes / originalSize) * 100).toFixed(1) : '100';

  return {
    width,
    height,
    viewBox,
    pathCount: paths.length,
    polygonCount: polygons.length,
    rectCount: rects.length,
    circleCount: circles.length,
    groupCount: groups.length,
    totalVectorNodes: allElements.length,
    colors: Array.from(colorMap),
    svgSizeBytes,
    sizeRatioPercent
  };
}

function renderSVGDataUI(container: HTMLElement, fileItem: FileItem, svgXml: string, engineName: string) {
  const svgData = parseSVGData(svgXml, fileItem.size);
  const blob = new Blob([svgXml], { type: 'image/svg+xml' });
  const svgUrl = URL.createObjectURL(blob);

  const colorSwatchesHTML = svgData.colors.length > 0
    ? svgData.colors.slice(0, 16).map(c => `
        <div class="color-swatch" style="background:${c}; font-size:0.68rem;" title="${c}">
          ${c}
        </div>
      `).join('')
    : '<span style="color: var(--text-muted); font-size:0.85rem;">Monochrome / Single Fill</span>';

  container.innerHTML = `
    <div class="inspector-detail">
      <!-- Controlled Size SVG Preview Box -->
      <div class="preview-box">
        ${svgXml}
      </div>

      <h3>${engineName} Data</h3>

      <!-- Inter-Tool Cross-Sending Action Bar -->
      <div class="inter-tool-bar">
        <label>⚡ Cross-Tool Data Pipeline: Send "${fileItem.name}" to another tool:</label>
        <div class="button-group">
          <button id="sendToOCRFromSVG" class="btn primary" style="font-size:0.78rem; padding:0.35rem 0.7rem;">
            🔤 Send to OCR Tool
          </button>
          <button id="sendToAnalyzerFromSVG" class="btn secondary" style="font-size:0.78rem; padding:0.35rem 0.7rem;">
            🎨 Send to Image Analyzer
          </button>
          <button id="sendToTrainingFromSVG" class="btn secondary" style="font-size:0.78rem; padding:0.35rem 0.7rem;">
            🎓 Send to Training Library
          </button>
        </div>
      </div>

      <!-- Interactive Action Buttons -->
      <div class="button-group" style="margin-top: 0.5rem;">
        <a href="${svgUrl}" download="${fileItem.name.replace(/\.[^/.]+$/, '')}.svg" class="btn primary">
          ⬇️ Download SVG Vector
        </a>
        <button id="copySVGCodeBtn" class="btn secondary">
          📋 Copy SVG Code
        </button>
        <button id="copySVGJSONBtn" class="btn secondary">
          💾 Copy Vector Data (JSON)
        </button>
      </div>

      <!-- Structured SVG Data Metrics -->
      <h4>📊 Vector Architecture & Metrics</h4>
      <table class="meta-table">
        <tr><th>Original Image File</th><td>${fileItem.name} (${formatBytes(fileItem.size)})</td></tr>
        <tr><th>Vector Output Size</th><td>${formatBytes(svgData.svgSizeBytes)} (${svgData.sizeRatioPercent}% of original size)</td></tr>
        <tr><th>Canvas ViewBox & Bounds</th><td><code>${svgData.viewBox}</code> (${svgData.width} × ${svgData.height})</td></tr>
        <tr><th>Vector Path Count (<code>&lt;path&gt;</code>)</th><td><strong>${svgData.pathCount.toLocaleString()} paths</strong></td></tr>
        <tr><th>Vector Elements</th><td>${svgData.totalVectorNodes.toLocaleString()} total nodes (${svgData.groupCount} groups, ${svgData.polygonCount} polygons, ${svgData.rectCount} rects, ${svgData.circleCount} circles)</td></tr>
        <tr><th>Color Palette Depth</th><td>${svgData.colors.length} unique vector colors</td></tr>
      </table>

      <!-- SVG Color Palette Swatches -->
      <h4>🎨 SVG Vector Palette Swatches</h4>
      <div class="palette-grid">
        ${colorSwatchesHTML}
      </div>

      <!-- SVG Code & Data View -->
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <h4 style="margin:0;">📄 SVG Raw XML Code View</h4>
        <span id="copyStatusText" style="font-size:0.8rem; color:#22c55e; display:none;">✅ Copied to clipboard!</span>
      </div>
      <div class="json-view">${escapeHTML(svgXml.slice(0, 1500))}${svgXml.length > 1500 ? '\n... [truncated]' : ''}</div>
    </div>
  `;

  // Inter-tool Pipeline Handlers
  container.querySelector('#sendToOCRFromSVG')?.addEventListener('click', async () => {
    const ocrOutput = document.getElementById('ocrOutput') as HTMLElement;
    if (ocrOutput) {
      switchTab('ocrTab');
      await runOCR(fileItem, ocrOutput);
    }
  });

  container.querySelector('#sendToAnalyzerFromSVG')?.addEventListener('click', async () => {
    const analyzerOutput = document.getElementById('analyzerOutput') as HTMLElement;
    if (analyzerOutput) {
      switchTab('analyzerTab');
      await analyzeImage(fileItem, analyzerOutput);
    }
  });

  container.querySelector('#sendToTrainingFromSVG')?.addEventListener('click', () => {
    switchTab('trainingTab');
  });

  // Copy SVG Code handler
  container.querySelector('#copySVGCodeBtn')?.addEventListener('click', () => {
    navigator.clipboard.writeText(svgXml);
    showCopyStatus(container);
  });

  // Copy Vector Data JSON handler
  container.querySelector('#copySVGJSONBtn')?.addEventListener('click', () => {
    const jsonString = JSON.stringify(svgData, null, 2);
    navigator.clipboard.writeText(jsonString);
    showCopyStatus(container);
  });
}

function showCopyStatus(container: HTMLElement) {
  const statusEl = container.querySelector('#copyStatusText') as HTMLElement;
  if (statusEl) {
    statusEl.style.display = 'inline';
    setTimeout(() => {
      statusEl.style.display = 'none';
    }, 2000);
  }
}

function switchTab(tabId: string) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.querySelector(`[data-tab="${tabId}"]`)?.classList.add('active');
  document.getElementById(tabId)?.classList.add('active');
}

function escapeHTML(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
