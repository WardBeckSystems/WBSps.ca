import { FileItem, TreeNode, ArchiveRecord } from './types';
import { ARCHIVE_BASE, itemUrl, itemFile } from './archive';
import { buildDirectoryTree, renderTreeUI, formatBytes } from './tree';
import { extractImageMetadata } from './imageExtractor';
import ImageTracer from 'imagetracerjs';
import { KNOBS_HIGH_DETAIL_PRESET, archiveTrace } from './svgConverter';
import { convert as traceToCad } from './traceCad';
import { extractDocxImages, extractPdfPagesAsImages, ExtractedImagePage } from './documentBreakout';

export let loadedFiles: FileItem[] = [];


let rootTreeNode: TreeNode | null = null;
let recentVisitedFiles: FileItem[] = [];

interface InventoryRecord {
  row: number;
  status: string;
  project: string;
  item: string;
  type: string;
  location: string;
  scanned_status: string;
}

let manualInventory: InventoryRecord[] = [];

async function loadManualInventory(): Promise<boolean> {
  try {
    const res = await fetch('/api/inventory');
    if (res.ok) {
      manualInventory = await res.json();
      console.log(`Loaded ${manualInventory.length} manual inventory records`);
      const keylistBodyEl = document.getElementById('keylistBody');
      if (keylistBodyEl && keylistBodyEl.style.display === 'flex') {
        renderKeylistUI();
      }
      return true;
    }
  } catch (err) {
    console.warn("Could not fetch manual inventory from API", err);
  }
  return false;
}
loadManualInventory();

// DOM Elements
const folderInput = document.getElementById('folderInput') as HTMLInputElement;
const fileInput = document.getElementById('fileInput') as HTMLInputElement;
const searchInput = document.getElementById('searchInput') as HTMLInputElement;

folderInput?.addEventListener('change', (e) => handleFileSelect(e));
document.getElementById('btnLoadArchive')?.addEventListener('click', () => loadArchive());
if (location.hash === '#archive') setTimeout(() => loadArchive(), 0);

/** Load everything in 2026/ from the catalog built by make_catalog.py; notes and OCR text become searchable. */
async function loadArchive() {
  statusProgressBanner.style.display = 'flex';
  statusProgressText.textContent = 'Loading the 2026 archive catalog...';
  statusProgressBar.style.width = '10%';
  try {
    const res = await fetch(ARCHIVE_BASE + '_catalog/catalog.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const records: ArchiveRecord[] = (await res.json()).files;
    const enc = (p: string) => ARCHIVE_BASE + p.split('/').map(encodeURIComponent).join('/');
    processFiles(records.map(r => ({
      relativePath: '2026/' + r.p,
      name: r.n,
      size: r.s,
      type: '',
      isImage: isImageFile(r.n),
      url: enc(r.p),
      thumbUrl: r.t ? enc(r.t) : undefined,
      ocrText: r.x || undefined,
      archive: { model: r.m, year: r.y, section: r.sec, category: r.cat, note: r.note ? enc(r.note) : undefined, original: r.o },
    })));
  } catch (err) {
    statusProgressText.textContent = `Could not load the 2026 catalog (${err}). Start the tool with "npm run dev" and build the catalog with make_catalog.py.`;
    statusProgressBar.style.width = '0%';
  }
}
fileInput?.addEventListener('change', (e) => handleFileSelect(e));

const statFiles = document.getElementById('statFiles') as HTMLElement;
const statDirs = document.getElementById('statDirs') as HTMLElement;
const statImages = document.getElementById('statImages') as HTMLElement;
const statSize = document.getElementById('statSize') as HTMLElement;

const statusProgressBanner = document.getElementById('statusProgressBanner') as HTMLElement;
const statusProgressText = document.getElementById('statusProgressText') as HTMLElement;
const statusProgressBar = document.getElementById('statusProgressBar') as HTMLElement;

const imagePreviewContainer = document.getElementById('imagePreviewContainer') as HTMLElement;
const treeContainer = document.getElementById('treeContainer') as HTMLElement;
const galleryContainer = document.getElementById('galleryContainer') as HTMLElement;
const masterInspectorContainer = document.getElementById('masterInspectorContainer') as HTMLElement;
const footerSlideshowTrack = document.getElementById('footerSlideshowTrack') as HTMLElement;

// Sorted View Elements
const btnOpenSortedView = document.getElementById('btnOpenSortedView') as HTMLButtonElement;
const sortedViewModal = document.getElementById('sortedViewModal') as HTMLElement;
const closeSortedViewModalBtn = document.getElementById('closeSortedViewModalBtn') as HTMLButtonElement;
const sortedViewTableContainer = document.getElementById('sortedViewTableContainer') as HTMLElement;
const sortedItemCountBadge = document.getElementById('sortedItemCountBadge') as HTMLElement;

const sortBtnName = document.getElementById('sortBtnName') as HTMLButtonElement;
const sortBtnSize = document.getElementById('sortBtnSize') as HTMLButtonElement;
const sortBtnExt = document.getElementById('sortBtnExt') as HTMLButtonElement;
const sortBtnCategory = document.getElementById('sortBtnCategory') as HTMLButtonElement;
const sortBtnStatus = document.getElementById('sortBtnStatus') as HTMLButtonElement;

let currentSortCriterion: 'name' | 'size' | 'ext' | 'category' | 'status' = 'name';

btnOpenSortedView?.addEventListener('click', () => {
  sortedViewModal.style.display = 'flex';
  renderSortedViewTable();
});

closeSortedViewModalBtn?.addEventListener('click', () => {
  sortedViewModal.style.display = 'none';
});

sortBtnName?.addEventListener('click', () => { setActiveSortBtn(sortBtnName); currentSortCriterion = 'name'; renderSortedViewTable(); });
sortBtnSize?.addEventListener('click', () => { setActiveSortBtn(sortBtnSize); currentSortCriterion = 'size'; renderSortedViewTable(); });
sortBtnExt?.addEventListener('click', () => { setActiveSortBtn(sortBtnExt); currentSortCriterion = 'ext'; renderSortedViewTable(); });
sortBtnCategory?.addEventListener('click', () => { setActiveSortBtn(sortBtnCategory); currentSortCriterion = 'category'; renderSortedViewTable(); });
sortBtnStatus?.addEventListener('click', () => { setActiveSortBtn(sortBtnStatus); currentSortCriterion = 'status'; renderSortedViewTable(); });

function setActiveSortBtn(targetBtn: HTMLButtonElement) {
  [sortBtnName, sortBtnSize, sortBtnExt, sortBtnCategory, sortBtnStatus].forEach(btn => {
    btn?.classList.toggle('active', btn === targetBtn);
  });
}

const sortedWordCloudContainer = document.getElementById('sortedWordCloudContainer') as HTMLElement;
const sortedFocusDetailsContainer = document.getElementById('sortedFocusDetailsContainer') as HTMLElement;

function renderSortedViewTable() {
  if (!sortedViewTableContainer) return;

  const itemsToDisplay: Array<{
    fileItem?: FileItem;
    name: string;
    path: string;
    size: number;
    ext: string;
    project: string;
    status: string;
    location: string;
  }> = [];

  if (loadedFiles.length > 0) {
    loadedFiles.forEach(f => {
      const ext = f.name.split('.').pop() || '';
      const cleanPath = f.relativePath.toLowerCase();
      const match = manualInventory.find(m => 
        (m.project && m.project.length >= 3 && cleanPath.includes(m.project.toLowerCase())) ||
        (m.item && m.item.length >= 4 && cleanPath.includes(m.item.toLowerCase()))
      );
      itemsToDisplay.push({
        fileItem: f,
        name: f.name,
        path: f.relativePath,
        size: f.size,
        ext: ext.toLowerCase(),
        project: match ? match.project : '',
        status: match ? match.scanned_status : '',
        location: match ? match.location : ''
      });
    });
  } else if (manualInventory.length > 0) {
    manualInventory.forEach(m => {
      itemsToDisplay.push({
        name: m.item || m.project,
        path: m.project,
        size: 0,
        ext: 'manual',
        project: m.project,
        status: m.scanned_status,
        location: m.location
      });
    });
  }

  // Perform Sorting
  itemsToDisplay.sort((a, b) => {
    if (currentSortCriterion === 'name') return a.name.localeCompare(b.name);
    if (currentSortCriterion === 'size') return b.size - a.size;
    if (currentSortCriterion === 'ext') return a.ext.localeCompare(b.ext);
    if (currentSortCriterion === 'category') return a.project.localeCompare(b.project);
    if (currentSortCriterion === 'status') return a.status.localeCompare(b.status);
    return 0;
  });

  if (sortedItemCountBadge) {
    sortedItemCountBadge.textContent = `${itemsToDisplay.length.toLocaleString()} Items`;
  }

  // Panel 1: Render 1/3 Scanned Data Table
  const limit = Math.min(itemsToDisplay.length, 500);
  const rowsHtml = itemsToDisplay.slice(0, limit).map((item, idx) => `
    <tr class="sorted-row" data-idx="${idx}" style="border-bottom:1px solid var(--border-color); cursor:pointer; background: ${idx % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent'}; transition:background 0.15s;">
      <td style="padding:4px 6px; color:var(--text-muted); font-size:0.68rem;">${idx + 1}</td>
      <td style="padding:4px 6px; font-weight:600; color:#f8fafc; font-size:0.72rem;">${escapeHTML(item.name)}</td>
      <td style="padding:4px 6px; color:#f472b6; font-weight:600; font-size:0.7rem;">${escapeHTML(item.project || '-')}</td>
      <td style="padding:4px 6px; color:#94a3b8; font-size:0.68rem;">${escapeHTML(item.path)}</td>
      <td style="padding:4px 6px; color:#38bdf8; font-size:0.7rem;">${item.size ? formatBytes(item.size) : '-'}</td>
      <td style="padding:4px 6px; font-size:0.68rem;">
        ${item.status ? `<span style="color:#38bdf8;">${escapeHTML(item.status)}</span>` : ''}
        ${item.location ? ` <span style="color:#f59e0b;">(${escapeHTML(item.location)})</span>` : ''}
      </td>
      <td style="padding:4px 6px; text-align:center;">
        ${item.fileItem ? `
          <button class="btn-inspect-sorted btn primary btn-sm" data-idx="${idx}" style="font-size:0.65rem; padding:1px 5px; background:#a855f7; color:#fff;">
            🔍 Inspect
          </button>
        ` : '-'}
      </td>
    </tr>
  `).join('');

  sortedViewTableContainer.innerHTML = `
    <table class="meta-table" style="width:100%; border-collapse:collapse; font-size:0.72rem;">
      <thead>
        <tr style="background:#1e293b; color:#a855f7; border-bottom:2px solid #a855f7; text-align:left;">
          <th style="padding:5px 6px;">#</th>
          <th style="padding:5px 6px;">File / Item Name</th>
          <th style="padding:5px 6px;">Project / Category</th>
          <th style="padding:5px 6px;">Relative Path</th>
          <th style="padding:5px 6px;">Size</th>
          <th style="padding:5px 6px;">Scan Status / Location</th>
          <th style="padding:5px 6px; text-align:center;">Action</th>
        </tr>
      </thead>
      <tbody>
        ${rowsHtml}
      </tbody>
    </table>
  `;

  // Row click & inspect handlers
  sortedViewTableContainer.querySelectorAll('.sorted-row').forEach(row => {
    row.addEventListener('click', (e) => {
      const targetBtn = (e.target as HTMLElement).closest('.btn-inspect-sorted');
      const idxStr = row.getAttribute('data-idx');
      if (idxStr !== null) {
        const idx = parseInt(idxStr);
        const selected = itemsToDisplay[idx];
        if (targetBtn && selected.fileItem) {
          inspectFileItem(selected.fileItem);
          sortedViewModal.style.display = 'none';
        } else if (selected) {
          renderFocusDetails(selected);
        }
      }
    });
  });

  // Panel 2: Render 2/3 Frequency Word Cloud
  renderWordCloud(itemsToDisplay);

  // Default Focus Details
  if (itemsToDisplay.length > 0) {
    renderFocusDetails(itemsToDisplay[0]);
  }
}

function renderWordCloud(items: Array<{ name: string; path: string; project: string; status: string; location: string; fileItem?: FileItem }>) {
  if (!sortedWordCloudContainer) return;

  const wordCounts: Record<string, number> = {};
  const stopWords = new Set(['and', 'the', 'for', 'with', 'this', 'that', 'from', 'file', 'png', 'jpg', 'jpeg', 'json', 'pdf', 'docx', 'txt', 'svg']);

  items.forEach(item => {
    const textSources = [item.name, item.path, item.project, item.status, item.location];
    if (item.fileItem && item.fileItem.ocrText) {
      textSources.push(item.fileItem.ocrText);
    }
    const combined = textSources.join(' ');
    const tokens = combined.toLowerCase().match(/\b[a-z0-9_\-]{3,}\b/g) || [];

    tokens.forEach(tok => {
      if (!stopWords.has(tok)) {
        wordCounts[tok] = (wordCounts[tok] || 0) + 1;
      }
    });
  });

  const sortedWords = Object.entries(wordCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 120);

  if (sortedWords.length === 0) {
    sortedWordCloudContainer.innerHTML = '<div class="empty-state">No words extracted for word cloud yet.</div>';
    return;
  }

  const maxFreq = sortedWords[0][1];
  const minFreq = sortedWords[sortedWords.length - 1][1];

  const colors = ['#38bdf8', '#a855f7', '#ec4899', '#f59e0b', '#10b981', '#6366f1', '#f43f5e', '#14b8a6'];

  const cloudHtml = sortedWords.map(([word, freq], idx) => {
    const norm = maxFreq === minFreq ? 1 : (freq - minFreq) / (maxFreq - minFreq);
    const fontSizeRem = (0.7 + norm * 1.6).toFixed(2);
    const color = colors[idx % colors.length];
    const opacity = (0.6 + norm * 0.4).toFixed(2);

    return `
      <span class="word-cloud-tag" data-word="${escapeHTML(word)}" data-freq="${freq}" 
            style="font-size:${fontSizeRem}rem; color:${color}; opacity:${opacity}; cursor:pointer; font-weight:${norm > 0.4 ? '700' : '500'}; padding:2px 5px; border-radius:3px; background:rgba(255,255,255,0.03); transition:transform 0.15s, background 0.15s;"
            title="Frequency: ${freq} occurrences">
        ${escapeHTML(word)} <sub style="font-size:0.6rem; opacity:0.7;">(${freq})</sub>
      </span>
    `;
  }).join('');

  sortedWordCloudContainer.innerHTML = cloudHtml;

  sortedWordCloudContainer.querySelectorAll('.word-cloud-tag').forEach(tag => {
    tag.addEventListener('mouseenter', () => {
      (tag as HTMLElement).style.transform = 'scale(1.15)';
      (tag as HTMLElement).style.background = 'rgba(168, 85, 247, 0.2)';
    });
    tag.addEventListener('mouseleave', () => {
      (tag as HTMLElement).style.transform = 'scale(1.0)';
      (tag as HTMLElement).style.background = 'rgba(255,255,255,0.03)';
    });
    tag.addEventListener('click', () => {
      const word = tag.getAttribute('data-word');
      const freq = tag.getAttribute('data-freq');
      if (word && sortedFocusDetailsContainer) {
        const matchingItems = items.filter(i => {
          const combined = `${i.name} ${i.path} ${i.project} ${i.status} ${i.location} ${i.fileItem?.ocrText || ''}`.toLowerCase();
          return combined.includes(word.toLowerCase());
        });

        sortedFocusDetailsContainer.innerHTML = `
          <div style="background:#0f172a; padding:0.6rem; border-radius:6px; border:1px solid #a855f7; margin-bottom:0.6rem;">
            <div style="font-size:0.85rem; font-weight:700; color:#a855f7;">☁️ Word Focus: <span style="color:#fff;">"${escapeHTML(word)}"</span></div>
            <div style="font-size:0.72rem; color:#94a3b8; margin-top:2px;">Total Occurrences: <strong style="color:#38bdf8;">${freq}</strong> | Matching Items: <strong style="color:#ec4899;">${matchingItems.length}</strong></div>
          </div>
          <div style="font-size:0.72rem; font-weight:700; color:#38bdf8; margin-bottom:4px;">Matching Items (${matchingItems.length}):</div>
          <div style="display:flex; flex-direction:column; gap:4px;">
            ${matchingItems.slice(0, 50).map(m => `
              <div style="padding:4px 6px; background:#1e293b; border-radius:4px; font-size:0.7rem; display:flex; justify-content:space-between; align-items:center;">
                <span style="color:#f8fafc; font-weight:600;">${escapeHTML(m.name)}</span>
                <span style="color:#f472b6;">${escapeHTML(m.project || 'General')}</span>
              </div>
            `).join('')}
          </div>
        `;
      }
    });
  });
}

function renderFocusDetails(item: { fileItem?: FileItem; name: string; path: string; size: number; ext: string; project: string; status: string; location: string }) {
  if (!sortedFocusDetailsContainer) return;

  sortedFocusDetailsContainer.innerHTML = `
    <div style="background:#0f172a; padding:0.75rem; border-radius:6px; border:1px solid #ec4899; margin-bottom:0.75rem;">
      <div style="font-weight:700; font-size:0.85rem; color:#ec4899; margin-bottom:4px;">📄 ${escapeHTML(item.name)}</div>
      <div style="font-size:0.72rem; color:#94a3b8; margin-bottom:2px;">Path: <span style="color:#e2e8f0;">${escapeHTML(item.path)}</span></div>
      <div style="font-size:0.72rem; color:#94a3b8; margin-bottom:2px;">Size: <span style="color:#38bdf8;">${item.size ? formatBytes(item.size) : 'N/A'}</span></div>
      <div style="font-size:0.72rem; color:#94a3b8; margin-bottom:2px;">Project/Category: <span style="color:#f472b6;">${escapeHTML(item.project || 'Uncategorized')}</span></div>
      <div style="font-size:0.72rem; color:#94a3b8;">Status: <span style="color:#38bdf8;">${escapeHTML(item.status || 'Pending')}</span> (${escapeHTML(item.location || 'N/A')})</div>
    </div>
    ${item.fileItem?.ocrText ? `
      <div style="background:#0f172a; padding:0.6rem; border-radius:6px; border:1px solid #38bdf8;">
        <div style="font-size:0.75rem; font-weight:700; color:#38bdf8; margin-bottom:4px;">📝 OCR Extracted Text Preview</div>
        <div style="font-size:0.68rem; font-family:monospace; color:#cbd5e1; white-space:pre-wrap; max-height:220px; overflow-y:auto; background:#020617; padding:6px; border-radius:4px;">${escapeHTML(item.fileItem.ocrText)}</div>
      </div>
    ` : `
      <div style="font-size:0.72rem; color:#64748b; font-style:italic; padding:0.5rem; text-align:center; background:#0f172a; border-radius:6px;">
        Click "Inspect" to view full document breakout, OCR overlay, and EXIF metadata.
      </div>
    `}
  `;
}

// View Mode & Keylist Elements
const btnViewTree = document.getElementById('btnViewTree') as HTMLButtonElement;
const btnViewKeylist = document.getElementById('btnViewKeylist') as HTMLButtonElement;
const treeSplitBody = document.getElementById('treeSplitBody') as HTMLElement;
const keylistBody = document.getElementById('keylistBody') as HTMLElement;

const btnGroupPrefix = document.getElementById('btnGroupPrefix') as HTMLButtonElement;
const btnGroupLocation = document.getElementById('btnGroupLocation') as HTMLButtonElement;
const btnGroupStatus = document.getElementById('btnGroupStatus') as HTMLButtonElement;
const btnGroupAllKeys = document.getElementById('btnGroupAllKeys') as HTMLButtonElement;

let currentKeylistGroupMode: 'prefix' | 'location' | 'status' | 'all' = 'prefix';

btnViewTree?.addEventListener('click', () => {
  btnViewTree.classList.add('active');
  btnViewKeylist.classList.remove('active');
  treeSplitBody.style.display = 'flex';
  keylistBody.style.display = 'none';
});

btnViewKeylist?.addEventListener('click', () => {
  btnViewKeylist.classList.add('active');
  btnViewTree.classList.remove('active');
  treeSplitBody.style.display = 'none';
  keylistBody.style.display = 'flex';
  renderKeylistUI();
});

btnGroupPrefix?.addEventListener('click', () => {
  setActiveGroupBtn(btnGroupPrefix);
  currentKeylistGroupMode = 'prefix';
  renderKeylistUI();
});

btnGroupLocation?.addEventListener('click', () => {
  setActiveGroupBtn(btnGroupLocation);
  currentKeylistGroupMode = 'location';
  renderKeylistUI();
});

btnGroupStatus?.addEventListener('click', () => {
  setActiveGroupBtn(btnGroupStatus);
  currentKeylistGroupMode = 'status';
  renderKeylistUI();
});

btnGroupAllKeys?.addEventListener('click', () => {
  setActiveGroupBtn(btnGroupAllKeys);
  currentKeylistGroupMode = 'all';
  renderKeylistUI();
});

const btnReloadInventoryHeader = document.getElementById('btnReloadInventoryHeader') as HTMLButtonElement;
btnReloadInventoryHeader?.addEventListener('click', async () => {
  const container = document.getElementById('keylistGroupsContainer');
  if (container) {
    container.innerHTML = `<div class="empty-state">🔄 Fetching inventory metadata from API...</div>`;
  }
  await loadManualInventory();
});

function setActiveGroupBtn(targetBtn: HTMLButtonElement) {
  [btnGroupPrefix, btnGroupLocation, btnGroupStatus, btnGroupAllKeys].forEach(btn => {
    btn?.classList.toggle('active', btn === targetBtn);
  });
}

searchInput?.addEventListener('input', () => {
  if (rootTreeNode) {
    renderTreeUI(rootTreeNode, treeContainer, inspectNode, searchInput.value);
  }
  if (keylistBody.style.display === 'flex') {
    renderKeylistUI();
  }
});

function renderKeylistUI() {
  const container = document.getElementById('keylistGroupsContainer');
  if (!container) return;

  if (manualInventory.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="display:flex; flex-direction:column; align-items:center; gap:0.75rem; padding:1.5rem; text-align:center;">
        <div style="font-size:0.85rem; color:#94a3b8;">No inventory metadata loaded.</div>
        <button id="btnReloadInventoryInState" class="btn primary btn-sm" style="background:#a855f7; color:#fff; font-weight:600; cursor:pointer; padding:0.4rem 0.8rem;">
          🔄 Reload Inventory Metadata
        </button>
      </div>
    `;
    document.getElementById('btnReloadInventoryInState')?.addEventListener('click', async () => {
      container.innerHTML = `<div class="empty-state">🔄 Fetching inventory metadata from API...</div>`;
      const ok = await loadManualInventory();
      if (!ok && manualInventory.length === 0) {
        renderKeylistUI();
      }
    });
    return;
  }

  const query = searchInput.value.toLowerCase().trim();

  if (currentKeylistGroupMode === 'prefix') {
    const groups: { [key: string]: InventoryRecord[] } = {
      '🎛️ M-Series Modules': [],
      '🎚️ L-Series Consoles': [],
      '📻 ST-Series & Consoles': [],
      '📺 TV & Broadcast Stations (CBC, CFPL, TVO, WSVN)': [],
      '📐 Technical Drawing Series (31106, 790236, 880651)': [],
      '📁 General / Other Projects': []
    };

    manualInventory.forEach(item => {
      const p = (item.project || '').toUpperCase();
      if (p.startsWith('M')) groups['🎛️ M-Series Modules'].push(item);
      else if (p.startsWith('L') || p.includes('L2042') || p.includes('L3242')) groups['🎚️ L-Series Consoles'].push(item);
      else if (p.startsWith('ST') || p.includes('2442') || p.includes('3642') || p.includes('880134')) groups['📻 ST-Series & Consoles'].push(item);
      else if (p.includes('CBC') || p.includes('CFPL') || p.includes('TVO') || p.includes('WSVN') || p.includes('CFBK')) groups['📺 TV & Broadcast Stations (CBC, CFPL, TVO, WSVN)'].push(item);
      else if (/^\d{4,}/.test(p)) groups['📐 Technical Drawing Series (31106, 790236, 880651)'].push(item);
      else groups['📁 General / Other Projects'].push(item);
    });

    let html = '';
    for (const [groupTitle, items] of Object.entries(groups)) {
      if (items.length === 0) continue;
      const filtered = query ? items.filter(i => (i.project + ' ' + i.item).toLowerCase().includes(query)) : items;
      if (query && filtered.length === 0) continue;

      html += `
        <div style="background:rgba(15,23,42,0.8); border:1px solid var(--border-color); border-radius:6px; padding:0.5rem;">
          <div style="font-weight:700; font-size:0.8rem; color:#a855f7; display:flex; justify-content:space-between; margin-bottom:0.4rem;">
            <span>${groupTitle}</span>
            <span class="tag-badge" style="background:#a855f7; color:#fff;">${filtered.length} items</span>
          </div>
          <div style="display:flex; flex-direction:column; gap:3px;">
            ${filtered.slice(0, 40).map(i => `
              <div class="keylist-item-btn" data-key="${escapeHTML(i.project || i.item)}" style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.03); padding:4px 6px; border-radius:4px; cursor:pointer; font-size:0.75rem;">
                <span style="color:#f8fafc; font-weight:600;">📌 ${escapeHTML(i.project || 'Key')} - <span style="color:#cbd5e1; font-weight:normal;">${escapeHTML(i.item)}</span></span>
                ${i.scanned_status ? `<span style="font-size:0.65rem; color:#38bdf8;">${escapeHTML(i.scanned_status)}</span>` : ''}
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }
    container.innerHTML = html;
  } else if (currentKeylistGroupMode === 'location') {
    const locMap: { [key: string]: InventoryRecord[] } = {};
    manualInventory.forEach(item => {
      const loc = item.location || 'Unspecified Storage';
      if (!locMap[loc]) locMap[loc] = [];
      locMap[loc].push(item);
    });

    let html = '';
    for (const [loc, items] of Object.entries(locMap)) {
      const filtered = query ? items.filter(i => (i.project + ' ' + i.item).toLowerCase().includes(query)) : items;
      if (query && filtered.length === 0) continue;

      html += `
        <div style="background:rgba(15,23,42,0.8); border:1px solid var(--border-color); border-radius:6px; padding:0.5rem;">
          <div style="font-weight:700; font-size:0.8rem; color:#f59e0b; display:flex; justify-content:space-between; margin-bottom:0.4rem;">
            <span>📦 ${escapeHTML(loc)}</span>
            <span class="tag-badge" style="background:#f59e0b; color:#0f172a;">${filtered.length} items</span>
          </div>
          <div style="display:flex; flex-direction:column; gap:3px;">
            ${filtered.slice(0, 40).map(i => `
              <div class="keylist-item-btn" data-key="${escapeHTML(i.project || i.item)}" style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.03); padding:4px 6px; border-radius:4px; cursor:pointer; font-size:0.75rem;">
                <span style="color:#f8fafc; font-weight:600;">📌 ${escapeHTML(i.project)} - ${escapeHTML(i.item)}</span>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }
    container.innerHTML = html;
  } else if (currentKeylistGroupMode === 'status') {
    const statMap: { [key: string]: InventoryRecord[] } = {};
    manualInventory.forEach(item => {
      const st = item.scanned_status || 'Unspecified Status';
      if (!statMap[st]) statMap[st] = [];
      statMap[st].push(item);
    });

    let html = '';
    for (const [st, items] of Object.entries(statMap)) {
      const filtered = query ? items.filter(i => (i.project + ' ' + i.item).toLowerCase().includes(query)) : items;
      if (query && filtered.length === 0) continue;

      html += `
        <div style="background:rgba(15,23,42,0.8); border:1px solid var(--border-color); border-radius:6px; padding:0.5rem;">
          <div style="font-weight:700; font-size:0.8rem; color:#38bdf8; display:flex; justify-content:space-between; margin-bottom:0.4rem;">
            <span>📄 ${escapeHTML(st)}</span>
            <span class="tag-badge" style="background:#0284c7; color:#fff;">${filtered.length} items</span>
          </div>
          <div style="display:flex; flex-direction:column; gap:3px;">
            ${filtered.slice(0, 40).map(i => `
              <div class="keylist-item-btn" data-key="${escapeHTML(i.project || i.item)}" style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.03); padding:4px 6px; border-radius:4px; cursor:pointer; font-size:0.75rem;">
                <span style="color:#f8fafc; font-weight:600;">📌 ${escapeHTML(i.project)} - ${escapeHTML(i.item)}</span>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }
    container.innerHTML = html;
  } else if (currentKeylistGroupMode === 'all') {
    const keyCounts: { [key: string]: number } = {};
    manualInventory.forEach(item => {
      const k = item.project || item.item;
      if (k) keyCounts[k] = (keyCounts[k] || 0) + 1;
    });

    const sortedKeys = Object.keys(keyCounts).sort();
    const filteredKeys = query ? sortedKeys.filter(k => k.toLowerCase().includes(query)) : sortedKeys;

    let html = `
      <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(130px, 1fr)); gap:4px;">
        ${filteredKeys.map(k => `
          <button class="keylist-item-btn toggle-btn" data-key="${escapeHTML(k)}" style="text-align:left; font-size:0.72rem; padding:4px 6px; background:#1e293b; color:#38bdf8; border:1px solid var(--border-color); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHTML(k)}">
            🔑 ${escapeHTML(k)} (${keyCounts[k]})
          </button>
        `).join('')}
      </div>
    `;
    container.innerHTML = html;
  }

  container.querySelectorAll('.keylist-item-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const key = (e.currentTarget as HTMLElement).getAttribute('data-key');
      if (key) {
        searchInput.value = key;
        if (rootTreeNode) {
          renderTreeUI(rootTreeNode, treeContainer, inspectNode, key);
        }
      }
    });
  });
}

const runSortsBtn = document.getElementById('runSortsBtn') as HTMLButtonElement;
runSortsBtn?.addEventListener('click', () => {
  runRustCategoryAndSortChartsUI();
});

// Interactive Resizable Sash Divider Event Logic
setupSashDividers();

function setupSashDividers() {
  const sash1 = document.getElementById('sashDivider1');
  const sash2 = document.getElementById('sashDivider2');
  const sashGallery = document.getElementById('sashDividerGallery');
  const colTree = document.getElementById('colTreePane');
  const colPreview = document.getElementById('colPreviewPane');
  const galleryContainer = document.getElementById('galleryContainer');
  const masterGrid = document.querySelector('.master-grid') as HTMLElement;

  if (!sash1 || !sash2 || !colTree || !colPreview || !masterGrid) return;

  let activeSash: HTMLElement | null = null;
  let startX = 0;
  let startTreeWidth = 0;
  let startPreviewWidth = 0;
  let startGalleryWidth = 0;

  sash1.addEventListener('mousedown', (e) => {
    activeSash = sash1;
    startX = e.clientX;
    startTreeWidth = colTree.getBoundingClientRect().width;
    sash1.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
  });

  sash2.addEventListener('mousedown', (e) => {
    activeSash = sash2;
    startX = e.clientX;
    startPreviewWidth = colPreview.getBoundingClientRect().width;
    sash2.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
  });

  sashGallery?.addEventListener('mousedown', (e) => {
    activeSash = sashGallery;
    startX = e.clientX;
    if (galleryContainer) {
      startGalleryWidth = galleryContainer.getBoundingClientRect().width;
    }
    sashGallery.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
  });

  window.addEventListener('mousemove', (e) => {
    if (!activeSash) return;
    const dx = e.clientX - startX;

    if (activeSash === sash1) {
      const newWidth = Math.max(180, startTreeWidth + dx);
      colTree.style.width = `${newWidth}px`;
      renderVisualDocumentOverlays();
    } else if (activeSash === sash2) {
      const newWidth = Math.max(240, startPreviewWidth + dx);
      colPreview.style.width = `${newWidth}px`;
      renderVisualDocumentOverlays();
    } else if (activeSash === sashGallery && galleryContainer) {
      const newWidth = Math.max(60, Math.min(320, startGalleryWidth - dx));
      galleryContainer.style.width = `${newWidth}px`;
    }
  });

  window.addEventListener('mouseup', () => {
    if (activeSash) {
      activeSash.classList.remove('dragging');
      activeSash = null;
      document.body.style.cursor = 'default';
      renderVisualDocumentOverlays();
    }
  });
}

function handleFileSelect(e: Event) {
  const target = e.target as HTMLInputElement;
  if (!target.files || target.files.length === 0) return;

  const files = target.files;
  const fileItems: FileItem[] = [];

  statusProgressBanner.style.display = 'flex';
  statusProgressText.textContent = `Reading ${files.length.toLocaleString()} files into workspace...`;
  statusProgressBar.style.width = '10%';

  setTimeout(() => {
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const relPath = file.webkitRelativePath || file.name;
      const lowerName = file.name.toLowerCase();

      // Disregard known scan JSON sidecars (*.exif.json, *.meta.json, *.sidecar.json)
      if (lowerName.endsWith('.exif.json') || lowerName.endsWith('.meta.json') || lowerName.endsWith('.sidecar.json')) {
        continue;
      }

      fileItems.push({
        file,
        relativePath: relPath,
        name: file.name,
        size: file.size,
        type: file.type,
        isImage: isImageFile(file.name)
      });
    }

    processFiles(fileItems);
  }, 50);
}

function isImageFile(filename: string): boolean {
  return /\.(jpe?g|png|gif|webp|svg|bmp|tiff?)$/i.test(filename);
}

function processFiles(files: FileItem[]) {
  loadedFiles = files;
  statusProgressText.textContent = `Building directory tree for ${files.length.toLocaleString()} items...`;
  statusProgressBar.style.width = '50%';

  setTimeout(() => {
    rootTreeNode = buildDirectoryTree(files);

    const totalFiles = files.length;
    const imageFiles = files.filter(f => f.isImage);
    const totalSize = files.reduce((acc, f) => acc + f.size, 0);

    let dirCount = 0;
    function countDirs(node: TreeNode) {
      if (node.isDir && node.path !== '') dirCount++;
      for (const child of node.children.values()) {
        if (child.isDir) countDirs(child);
      }
    }
    countDirs(rootTreeNode);

    statFiles.textContent = totalFiles.toLocaleString();
    statDirs.textContent = dirCount.toLocaleString();
    statImages.textContent = imageFiles.length.toLocaleString();
    statSize.textContent = formatBytes(totalSize);

    statusProgressText.textContent = `Rendering File Explorer & Image Gallery...`;
    statusProgressBar.style.width = '85%';

    renderTreeUI(rootTreeNode, treeContainer, inspectNode, searchInput.value);
    renderVisualGallery(imageFiles);

    statusProgressText.textContent = `✅ Successfully indexed ${totalFiles.toLocaleString()} files!`;
    statusProgressBar.style.width = '100%';

    setTimeout(() => {
      statusProgressBanner.style.display = 'none';
    }, 2500);

    if (imageFiles.length > 0) {
      inspectFileItem(imageFiles[0]);
    } else if (files.length > 0) {
      inspectFileItem(files[0]);
    }
  }, 50);
}

function renderVisualGallery(imageFiles: FileItem[], selectedItem?: FileItem | null) {
  galleryContainer.innerHTML = '';
  if (imageFiles.length === 0) {
    galleryContainer.innerHTML = '<div class="empty-state" style="font-size:0.7rem;">No media or CAD files found in selection.</div>';
    return;
  }

  const displayLimit = Math.min(imageFiles.length, 300);
  for (let i = 0; i < displayLimit; i++) {
    const item = imageFiles[i];
    const card = document.createElement('div');
    const isSelected = selectedItem && (item.relativePath === selectedItem.relativePath);
    card.className = 'gallery-card' + (isSelected ? ' selected' : '');

    const isDxf = item.name.toLowerCase().endsWith('.dxf');
    const icon = isDxf ? '📐' : '🖼️';
    const url = item.thumbUrl ?? itemUrl(item);
    
    card.innerHTML = `
      <img src="${url}" alt="${item.name}" class="gallery-thumb" loading="lazy" />
      <div class="gallery-title" title="${item.name}">${icon} ${item.name}</div>
    `;

    card.addEventListener('click', () => {
      galleryContainer.querySelectorAll('.gallery-card.selected').forEach(el => el.classList.remove('selected'));
      card.classList.add('selected');
      inspectFileItem(item);
    });

    galleryContainer.appendChild(card);
    if (isSelected) {
      setTimeout(() => {
        card.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }, 50);
    }
  }
}

function isPreviewableFile(f: FileItem): boolean {
  if (f.isImage) return true;
  const lower = f.name.toLowerCase();
  return lower.endsWith('.dxf') || lower.endsWith('.dwg') || lower.endsWith('.pdf');
}

async function inspectNode(node: TreeNode) {
  if (node.fileItem) {
    const parentPath = node.fileItem.relativePath.includes('/')
      ? node.fileItem.relativePath.substring(0, node.fileItem.relativePath.lastIndexOf('/'))
      : '';

    const folderFiles = loadedFiles.filter(f => isPreviewableFile(f) && (
      parentPath === ''
        ? !f.relativePath.includes('/')
        : f.relativePath.startsWith(parentPath + '/')
    ));

    const filesToRender = folderFiles.length > 0 ? folderFiles : loadedFiles.filter(f => isPreviewableFile(f));
    renderVisualGallery(filesToRender, node.fileItem);
    await inspectFileItem(node.fileItem);
  } else if (node.isDir) {
    const folderFiles: FileItem[] = [];
    function collectFolderFiles(n: TreeNode) {
      if (n.fileItem && isPreviewableFile(n.fileItem)) {
        folderFiles.push(n.fileItem);
      }
      for (const child of n.children.values()) {
        collectFolderFiles(child);
      }
    }
    collectFolderFiles(node);
    const selectedItem = folderFiles.length > 0 ? folderFiles[0] : null;
    renderVisualGallery(folderFiles, selectedItem);
    if (folderFiles.length > 0) {
      await inspectFileItem(folderFiles[0]);
    }
  }
}

// Overlay State Flags
let showOcrBoxes = true;
let showTextOverlay = true;
let showTitleBlock = false;
let showFaceOverlay = false;
let showSchematicLines = false;
let showSvgVector = false;
let currentInspectedFileItem: FileItem | null = null;
let currentInspectedOcrData: any = null;
let currentInspectedPhotoData: any = null;
let currentInspectedAnalyzerData: any = null;
let currentInspectedSvgData: any = null;
let currentInspectedImgUrl: string = '';

// Overlay Controls
const btnToggleOcrBoxes = document.getElementById('btnToggleOcrBoxes') as HTMLButtonElement;
const btnToggleTextOverlay = document.getElementById('btnToggleTextOverlay') as HTMLButtonElement;
const btnToggleTitleBlock = document.getElementById('btnToggleTitleBlock') as HTMLButtonElement;
const btnToggleFaceOverlay = document.getElementById('btnToggleFaceOverlay') as HTMLButtonElement;
const btnToggleSchematicLines = document.getElementById('btnToggleSchematicLines') as HTMLButtonElement;
const btnToggleSvgVector = document.getElementById('btnToggleSvgVector') as HTMLButtonElement;
const btnFullDocViewer = document.getElementById('btnFullDocViewer') as HTMLButtonElement;

const fullDocModal = document.getElementById('fullDocModal') as HTMLElement;
const fullDocModalBody = document.getElementById('fullDocModalBody') as HTMLElement;
const closeFullDocModalBtn = document.getElementById('closeFullDocModalBtn') as HTMLButtonElement;

const modalBtnToggleOcrBoxes = document.getElementById('modalBtnToggleOcrBoxes') as HTMLButtonElement;
const modalBtnToggleTextOverlay = document.getElementById('modalBtnToggleTextOverlay') as HTMLButtonElement;
const modalBtnToggleTitleBlock = document.getElementById('modalBtnToggleTitleBlock') as HTMLButtonElement;
const modalBtnToggleFaceOverlay = document.getElementById('modalBtnToggleFaceOverlay') as HTMLButtonElement;
const modalBtnToggleSchematicLines = document.getElementById('modalBtnToggleSchematicLines') as HTMLButtonElement;
const modalBtnToggleSvgVector = document.getElementById('modalBtnToggleSvgVector') as HTMLButtonElement;

btnToggleOcrBoxes?.addEventListener('click', () => {
  showOcrBoxes = !showOcrBoxes;
  btnToggleOcrBoxes.classList.toggle('active', showOcrBoxes);
  modalBtnToggleOcrBoxes?.classList.toggle('active', showOcrBoxes);
  renderVisualDocumentOverlays();
});

btnToggleTextOverlay?.addEventListener('click', () => {
  showTextOverlay = !showTextOverlay;
  btnToggleTextOverlay.classList.toggle('active', showTextOverlay);
  modalBtnToggleTextOverlay?.classList.toggle('active', showTextOverlay);
  renderVisualDocumentOverlays();
});

btnToggleTitleBlock?.addEventListener('click', () => {
  showTitleBlock = !showTitleBlock;
  btnToggleTitleBlock.classList.toggle('active', showTitleBlock);
  modalBtnToggleTitleBlock?.classList.toggle('active', showTitleBlock);
  renderVisualDocumentOverlays();
});

btnToggleFaceOverlay?.addEventListener('click', () => {
  showFaceOverlay = !showFaceOverlay;
  btnToggleFaceOverlay.classList.toggle('active', showFaceOverlay);
  modalBtnToggleFaceOverlay?.classList.toggle('active', showFaceOverlay);
  renderVisualDocumentOverlays();
});

btnToggleSchematicLines?.addEventListener('click', () => {
  showSchematicLines = !showSchematicLines;
  btnToggleSchematicLines.classList.toggle('active', showSchematicLines);
  modalBtnToggleSchematicLines?.classList.toggle('active', showSchematicLines);
  renderVisualDocumentOverlays();
});

btnToggleSvgVector?.addEventListener('click', () => {
  showSvgVector = !showSvgVector;
  btnToggleSvgVector.classList.toggle('active', showSvgVector);
  modalBtnToggleSvgVector?.classList.toggle('active', showSvgVector);
  renderVisualDocumentOverlays();
});

modalBtnToggleOcrBoxes?.addEventListener('click', () => {
  showOcrBoxes = !showOcrBoxes;
  btnToggleOcrBoxes?.classList.toggle('active', showOcrBoxes);
  modalBtnToggleOcrBoxes.classList.toggle('active', showOcrBoxes);
  renderVisualDocumentOverlays();
});

modalBtnToggleTextOverlay?.addEventListener('click', () => {
  showTextOverlay = !showTextOverlay;
  btnToggleTextOverlay?.classList.toggle('active', showTextOverlay);
  modalBtnToggleTextOverlay.classList.toggle('active', showTextOverlay);
  renderVisualDocumentOverlays();
});

modalBtnToggleTitleBlock?.addEventListener('click', () => {
  showTitleBlock = !showTitleBlock;
  btnToggleTitleBlock?.classList.toggle('active', showTitleBlock);
  modalBtnToggleTitleBlock.classList.toggle('active', showTitleBlock);
  renderVisualDocumentOverlays();
});

modalBtnToggleFaceOverlay?.addEventListener('click', () => {
  showFaceOverlay = !showFaceOverlay;
  btnToggleFaceOverlay?.classList.toggle('active', showFaceOverlay);
  modalBtnToggleFaceOverlay.classList.toggle('active', showFaceOverlay);
  renderVisualDocumentOverlays();
});

modalBtnToggleSchematicLines?.addEventListener('click', () => {
  showSchematicLines = !showSchematicLines;
  btnToggleSchematicLines?.classList.toggle('active', showSchematicLines);
  modalBtnToggleSchematicLines.classList.toggle('active', showSchematicLines);
  renderVisualDocumentOverlays();
});

modalBtnToggleSvgVector?.addEventListener('click', () => {
  showSvgVector = !showSvgVector;
  btnToggleSvgVector?.classList.toggle('active', showSvgVector);
  modalBtnToggleSvgVector.classList.toggle('active', showSvgVector);
  renderVisualDocumentOverlays();
});

btnFullDocViewer?.addEventListener('click', () => {
  if (!currentInspectedFileItem) return;
  fullDocModal.style.display = 'flex';
  renderVisualDocumentOverlays();
});

closeFullDocModalBtn?.addEventListener('click', () => {
  fullDocModal.style.display = 'none';
});

async function inspectFileItem(fileItem: FileItem) {
  // Push to recent 5-item slideshow
  pushRecentSlideshow(fileItem);
  currentInspectedFileItem = fileItem;

  // 1. UPDATE LEFT 1/3 IMAGE PREVIEW
  const isPdf = fileItem.name.toLowerCase().endsWith('.pdf') || fileItem.type === 'application/pdf';
  if (fileItem.isImage) {
    currentInspectedImgUrl = itemUrl(fileItem);
  } else if (isPdf) {
    currentInspectedImgUrl = itemUrl(fileItem);
    imagePreviewContainer.innerHTML = `
      <div style="width:100%; height:100%; display:flex; flex-direction:column; background:#0f172a; position:relative;">
        <div style="display:flex; justify-content:space-between; align-items:center; padding:3px 6px; background:#1e293b; border-bottom:1px solid var(--border-color); font-size:0.7rem;">
          <span style="color:#ec4899; font-weight:700;">📄 PDF Breakout Viewer: ${escapeHTML(fileItem.name)}</span>
          <div style="display:flex; gap:4px;">
            <button id="btnPdfBreakoutHeader" class="btn primary btn-sm" style="font-size:0.65rem; padding:1px 6px; background:#ec4899; color:#fff;">🚀 Break Out Fullscreen</button>
            <a href="${currentInspectedImgUrl}" target="_blank" class="btn secondary btn-sm" style="font-size:0.65rem; padding:1px 6px; text-decoration:none;">↗ Open in Tab</a>
          </div>
        </div>
        <iframe src="${currentInspectedImgUrl}#toolbar=1&navpanes=1" style="flex:1; width:100%; border:none; background:#525659;" title="PDF Breakout Frame"></iframe>
      </div>
    `;
    setTimeout(() => {
      document.getElementById('btnPdfBreakoutHeader')?.addEventListener('click', () => {
        openPdfBreakoutModal(fileItem, currentInspectedImgUrl);
      });
    }, 50);
  } else {
    currentInspectedImgUrl = '';
    imagePreviewContainer.innerHTML = `
      <div class="empty-state" style="color:var(--accent);">
        📄 Non-Image File Preview<br>
        <span style="font-size:1.1rem; font-weight:700; color:#fff;">${escapeHTML(fileItem.name)}</span>
      </div>
    `;
  }

  // 1b. WHAT THE ARCHIVE'S EXTRACTORS FOUND (timelines/*.py via /api/file): archive items only
  showArchiveFacts(fileItem);

  // 2. FETCH EVERYTHING ABOUT THE FILE FROM RUST MICRO-API
  masterInspectorContainer.innerHTML = `<div class="empty-state">Extracting OCR, EXIF, Image Analysis, SVG Vector, Face Detection, and Sidecar Tags...</div>`;

  let rustOcr: any = null;
  let rustAnalyzer: any = null;
  let rustSvg: any = null;
  let rustPhoto: any = null;
  let rustDocx: any = null;

  const fileBytes = await (await itemFile(fileItem)).arrayBuffer();

  const isDocx = fileItem.name.toLowerCase().endsWith('.docx') || fileItem.name.toLowerCase().endsWith('.doc');
  const isDxf = fileItem.name.toLowerCase().endsWith('.dxf');

  let rustDxf: any = null;

  if (fileItem.isImage) {
    try {
      const [ocrR, anR, svgR, photoR] = await Promise.all([
        fetch('/api/ocr', { method: 'POST', body: fileBytes }),
        fetch('/api/analyze-image', { method: 'POST', body: fileBytes }),
        fetch('/api/to-svg', { method: 'POST', body: fileBytes }),
        fetch('/api/photo-id', { method: 'POST', body: fileBytes })
      ]);

      if (ocrR.ok) {
        rustOcr = await ocrR.json();
        if (rustOcr && rustOcr.extracted_text) {
          fileItem.ocrText = rustOcr.extracted_text;
        }
      }
      if (anR.ok) rustAnalyzer = await anR.json();
      if (svgR.ok) rustSvg = await svgR.json();
      if (photoR.ok) rustPhoto = await photoR.json();
    } catch (err) {
      console.warn("Rust API offline, using partial local extraction", err);
    }

    if (!rustSvg || !rustSvg.path_count || rustSvg.path_count < 200) {
      try {
        const highDetailSvg = await new Promise<any>((resolve) => {
          const url = itemUrl(fileItem);
          ImageTracer.imageToSVG(
            url,
            (svgString: string) => {
              URL.revokeObjectURL(url);
              const pathMatches = svgString.match(/<path/g);
              resolve({
                svg_xml: svgString,
                path_count: pathMatches ? pathMatches.length : 0
              });
            },
            KNOBS_HIGH_DETAIL_PRESET
          );
        });
        if (highDetailSvg && highDetailSvg.path_count > 0) {
          rustSvg = highDetailSvg;
        }
      } catch (err) {
        console.warn("High detail ImageTracer error", err);
      }
    }
  } else if (isDocx) {
    try {
      const docxR = await fetch('/api/docx-parse', { method: 'POST', body: fileBytes });
      if (docxR.ok) rustDocx = await docxR.json();
    } catch (err) {
      console.warn("DOCX parser offline", err);
    }
  } else if (isDxf) {
    try {
      const [dxfParseR, dxfRenderR] = await Promise.all([
        fetch('/api/dxf-parse', { method: 'POST', body: fileBytes }),
        fetch('/api/dxf-render', { method: 'POST', body: fileBytes })
      ]);

      if (dxfParseR.ok) {
        rustDxf = await dxfParseR.json();
        if (rustDxf && rustDxf.extracted_text && rustDxf.extracted_text.length > 0) {
          fileItem.ocrText = rustDxf.extracted_text.join('\n');
        }
      }

      if (dxfRenderR.ok) {
        const dxfData = await dxfRenderR.json();
        if (dxfData.png_base64) {
          currentInspectedImgUrl = dxfData.png_base64;
          imagePreviewContainer.innerHTML = `
            <div style="width:100%; height:100%; display:flex; flex-direction:column; background:#020617; position:relative; align-items:center; justify-content:center; overflow:hidden;">
              <div style="position:absolute; top:4px; left:6px; background:rgba(15,23,42,0.85); padding:3px 8px; border-radius:4px; border:1px solid #38bdf8; font-size:0.7rem; color:#38bdf8; font-weight:700; z-index:10;">
                📐 DXF Vector Drawing View: ${escapeHTML(fileItem.name)}
              </div>
              <img src="${currentInspectedImgUrl}" style="max-width:100%; max-height:100%; object-fit:contain;" alt="DXF Drawing Render" />
            </div>
          `;
        }
      }
    } catch (err) {
      console.warn("DXF parser or renderer offline", err);
    }
  }

  let docBreakoutPages: ExtractedImagePage[] = [];
  if (isPdf) {
    docBreakoutPages = await extractPdfPagesAsImages(await itemFile(fileItem));
  } else if (isDocx) {
    docBreakoutPages = await extractDocxImages(await itemFile(fileItem));
  }

  if (docBreakoutPages.length > 0) {
    imagePreviewContainer.innerHTML = `
      <div style="width:100%; height:100%; display:flex; flex-direction:column; background:#090d16; position:relative;">
        <div style="display:flex; justify-content:space-between; align-items:center; padding:3px 6px; background:#1e293b; border-bottom:1px solid var(--border-color); font-size:0.7rem; flex-shrink:0;">
          <span style="color:#ec4899; font-weight:700;">🚀 Broken Out Document (${docBreakoutPages.length} Image Pages / Media Assets): ${escapeHTML(fileItem.name)}</span>
          <div style="display:flex; gap:4px;">
            <button id="btnBreakoutFullGallery" class="btn primary btn-sm" style="font-size:0.65rem; padding:1px 6px; background:#ec4899; color:#fff;">🚀 Fullscreen Gallery</button>
          </div>
        </div>
        <div style="flex:1; overflow-y:auto; padding:0.4rem; display:flex; flex-direction:column; gap:0.5rem; align-items:center;">
          ${docBreakoutPages.map(p => `
            <div style="background:#0f172a; border:1px solid var(--border-color); padding:0.3rem; border-radius:4px; max-width:100%; text-align:center;">
              <div style="font-size:0.68rem; color:#38bdf8; font-weight:700; margin-bottom:3px;">${escapeHTML(p.title)} (${p.width}x${p.height} px)</div>
              <img src="${p.dataUrl}" style="max-width:100%; max-height:480px; object-fit:contain; border-radius:2px;" />
            </div>
          `).join('')}
        </div>
      </div>
    `;
    setTimeout(() => {
      document.getElementById('btnBreakoutFullGallery')?.addEventListener('click', () => {
        openDocumentBreakoutModal(fileItem, docBreakoutPages);
      });
    }, 50);
  }

  currentInspectedOcrData = rustOcr;
  currentInspectedPhotoData = rustPhoto;
  currentInspectedAnalyzerData = rustAnalyzer;
  currentInspectedSvgData = rustSvg;

  if (fileItem.isImage) {
    renderVisualDocumentOverlays();
  }

  let metaPhotos: any[] = [];
  if (fileItem.isImage) {
    metaPhotos = await generateMetaPhotos(fileItem, rustAnalyzer, rustPhoto, rustOcr);
  } else if (docBreakoutPages.length > 0) {
    metaPhotos = docBreakoutPages.map(p => ({
      id: p.id,
      title: p.title,
      dataUrl: p.dataUrl,
      width: p.width,
      height: p.height,
      x: 0,
      y: 0
    }));
  }

  const meta = await extractImageMetadata(fileItem);
  const fileTags = extractFilenameTags(fileItem.name);

  // Match Inventory Records from WBSps.ca SCANNING MANUAL INVENTORY.xlsx
  const cleanPath = (fileItem.relativePath || fileItem.name).toLowerCase();
  const fileTokens = fileItem.name.toLowerCase().replace(/[^a-z0-9]+/g, ' ').split(' ').filter(t => t.length >= 3);
  
  const inventoryMatches = manualInventory.filter(rec => {
    if (!rec.project && !rec.item) return false;
    const projLower = (rec.project || '').toLowerCase();
    const itemLower = (rec.item || '').toLowerCase();

    if (projLower.length >= 3 && cleanPath.includes(projLower)) return true;
    if (itemLower.length >= 4 && cleanPath.includes(itemLower)) return true;

    for (const token of fileTokens) {
      if ((projLower.length >= 3 && projLower.includes(token)) || (itemLower.length >= 4 && itemLower.includes(token))) return true;
    }
    return false;
  }).slice(0, 6);

  // Render Everything in Right Column
  masterInspectorContainer.innerHTML = `
    <!-- PDF DOCUMENT BREAKOUT CARD -->
    ${isPdf ? `
    <div class="data-card" style="border: 2px solid #ec4899; background: rgba(236, 72, 153, 0.08);">
      <h4 style="color:#ec4899;">🚀 PDF DOCUMENT BREAKOUT & MULTI-PAGE VIEWER</h4>
      <div style="font-size:0.7rem; color:#cbd5e1; margin-bottom:0.2rem;">
        Interactive PDF Document. Break out full document into standalone window or browser tab:
      </div>
      <table class="meta-table">
        <tr><th>Document Title</th><td><strong>${escapeHTML(fileItem.name)}</strong></td></tr>
        <tr><th>Format</th><td><span class="tag-badge" style="background:#ec4899; color:#fff;">PDF Document</span></td></tr>
        <tr><th>File Size</th><td>${formatBytes(fileItem.size)}</td></tr>
        <tr><th>Path</th><td><code>${escapeHTML(fileItem.relativePath)}</code></td></tr>
      </table>
      <div style="display:flex; gap:4px; margin-top:0.3rem;">
        <button id="btnInspectorPdfBreakout" class="btn primary" style="flex:1; font-size:0.68rem; background:#ec4899; color:#fff;">
          🚀 Break Out Fullscreen Modal
        </button>
        <a href="${currentInspectedImgUrl}" target="_blank" class="btn secondary" style="flex:1; text-align:center; font-size:0.68rem; text-decoration:none;">
          ↗ Open in New Tab
        </a>
      </div>
    </div>
    ` : ''}

    <!-- MASTER MANUAL INVENTORY MATCH (From WBSps.ca SCANNING MANUAL INVENTORY.xlsx) -->
    ${inventoryMatches.length > 0 ? `
    <div class="data-card" style="border: 2px solid #a855f7; background: rgba(168, 85, 247, 0.08);">
      <h4 style="color:#a855f7;">📋 MASTER MANUAL INVENTORY MATCH (${inventoryMatches.length} Records)</h4>
      <div style="font-size:0.75rem; color:#cbd5e1; margin-bottom:0.4rem;">
        Cross-referenced key meta from <code>WBSps.ca SCANNING MANUAL INVENTORY.xlsx</code>:
      </div>
      <div style="display:flex; flex-direction:column; gap:0.4rem;">
        ${inventoryMatches.map(m => `
          <div style="background: rgba(15, 23, 42, 0.6); padding: 0.45rem; border-radius: 4px; border: 1px solid rgba(168, 85, 247, 0.3); font-size: 0.78rem;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 2px;">
              <strong style="color:#f472b6;">📌 Project / Code: ${m.project}</strong>
              <span class="tag-badge" style="background:#a855f7; color:#fff; font-size:0.68rem;">Row #${m.row}</span>
            </div>
            <div style="color:#e2e8f0; font-weight:600; margin-bottom: 2px;">Item: ${m.item}</div>
            <div style="display:flex; flex-wrap:wrap; gap:8px; font-size:0.72rem; color:#cbd5e1; margin-top:3px;">
              ${m.scanned_status ? `<span><strong>Scanned:</strong> <span style="color:#38bdf8; font-weight:600;">${m.scanned_status}</span></span>` : ''}
              ${m.location ? `<span><strong>Location:</strong> <span style="color:#f59e0b; font-weight:600;">${m.location}</span></span>` : ''}
              ${m.status ? `<span><strong>Flag:</strong> ${m.status}</span>` : ''}
            </div>
          </div>
        `).join('')}
      </div>
    </div>
    ` : ''}

    <!-- DXF VECTOR DRAWING DATA INSPECTOR CARD -->
    ${rustDxf ? `
    <div class="data-card" style="border: 2px solid #38bdf8; background: rgba(56, 189, 248, 0.08);">
      <h4 style="color:#38bdf8;">📐 AUTOCAD DXF VECTOR ANALYSIS</h4>
      <table class="meta-table">
        <tr><th>Format / Version</th><td><strong style="color:#38bdf8;">${escapeHTML(rustDxf.acad_version)}</strong></td></tr>
        <tr><th>Total Lines</th><td>${rustDxf.line_count.toLocaleString()} lines</td></tr>
        <tr><th>Layers Detected (${rustDxf.layers ? rustDxf.layers.length : 0})</th><td><span style="color:#f472b6;">${rustDxf.layers ? rustDxf.layers.slice(0, 10).join(', ') : '-'}</span></td></tr>
      </table>
      ${rustDxf.entity_counts && Object.keys(rustDxf.entity_counts).length > 0 ? `
        <div style="margin-top:6px; font-size:0.7rem; font-weight:700; color:#e2e8f0;">CAD Entities Breakdown:</div>
        <div style="display:flex; flex-wrap:wrap; gap:4px; margin-top:3px;">
          ${Object.entries(rustDxf.entity_counts).map(([ent, count]) => `
            <span class="tag-badge" style="background:#0f172a; border:1px solid #38bdf8; color:#38bdf8; font-size:0.68rem;">${ent}: <strong>${count}</strong></span>
          `).join('')}
        </div>
      ` : ''}
      ${rustDxf.extracted_text && rustDxf.extracted_text.length > 0 ? `
        <div style="margin-top:6px; font-size:0.7rem; font-weight:700; color:#38bdf8;">Extracted CAD Text Annotations (${rustDxf.extracted_text.length}):</div>
        <div style="font-size:0.68rem; font-family:monospace; color:#cbd5e1; white-space:pre-wrap; max-height:140px; overflow-y:auto; background:#020617; padding:5px; border-radius:4px; margin-top:2px;">${escapeHTML(rustDxf.extracted_text.join('\n'))}</div>
      ` : ''}
    </div>
    ` : ''}
    <div class="data-card">
      <h4>📁 FILE TAGS (Filename & Extension Basis)</h4>
      <div class="tag-cloud">
        ${fileTags.map(t => `<span class="tag-badge" style="background:#0284c7; color:#fff;">📁 #${t}</span>`).join(' ')}
      </div>
    </div>

    <!-- EXTRACTED SUB-AREA META-PHOTOS & CROPPED ASSETS -->
    ${metaPhotos.length > 0 ? `
    <div class="data-card" style="border: 2px solid #10b981; background: rgba(16, 185, 129, 0.08);">
      <h4 style="color:#10b981;">📸 EXTRACTED SUB-AREA META-PHOTOS (${metaPhotos.length} Sub-Assets)</h4>
      <div style="font-size:0.75rem; color:#cbd5e1; margin-bottom:0.3rem;">
        Sub-region photos automatically extracted & cropped from title blocks, face areas, text regions, and panel sub-quadrants.
      </div>
      <div class="meta-photo-grid">
        ${metaPhotos.map(mp => `
          <div class="meta-photo-card">
            <img src="${mp.dataUrl}" alt="${mp.title}" class="meta-photo-thumb" />
            <div class="meta-photo-title" title="${mp.title}">${mp.title}</div>
            <div class="meta-photo-meta">${mp.width}x${mp.height} px @ (${mp.x}, ${mp.y})</div>
            <div style="display:flex; gap:3px; margin-top:2px;">
              <button class="btn-preview-subphoto" data-url="${mp.dataUrl}" style="flex:1; padding:2px 4px; font-size:0.65rem; background:var(--card-bg); color:#fff; border:none; border-radius:3px; cursor:pointer;" title="View this sub-photo preview">
                🔍 View
              </button>
              <button class="btn-download-subphoto" data-url="${mp.dataUrl}" data-name="${fileItem.name.replace(/\.[^/.]+$/, "")}_${mp.id}.png" style="flex:1; padding:2px 4px; font-size:0.65rem; background:#10b981; color:#fff; border:none; border-radius:3px; cursor:pointer;" title="Extract & download sub-photo PNG">
                ⬇️ Extract
              </button>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
    ` : ''}

    <!-- FACE DETECTION, EXTRACTION & IDENTIFICATION / MATCHING -->
    ${rustPhoto && rustPhoto.face_detection ? `
    <div class="data-card">
      <h4>👤 FACE DETECTION, EXTRACTION & IDENTIFICATION / MATCHING</h4>
      <table class="meta-table">
        <tr><th>Faces Detected</th><td><strong>${rustPhoto.face_detection.faces_detected} face(s)</strong></td></tr>
        <tr><th>Portrait Mode</th><td>${rustPhoto.face_detection.is_portrait ? 'YES 👤' : 'NO'}</td></tr>
        <tr><th>Face Bounding Boxes</th><td>${rustPhoto.face_detection.face_boxes.length} bounding box(es)</td></tr>
      </table>
      
      ${rustPhoto.face_detection.face_boxes.length > 0 ? `
      <div style="margin-top: 0.5rem; font-size: 0.8rem; background: rgba(236,72,153,0.1); padding: 0.5rem; border-radius: 4px; border: 1px solid rgba(236,72,153,0.3);">
        <strong>Detected Face Feature Signatures & Matcher:</strong>
        <div style="margin-top: 0.3rem;">
          ${rustPhoto.face_detection.face_boxes.map((box: any, idx: number) => `
            <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom: 4px;">
              <span>👤 Face #${idx+1}: (${box.x}, ${box.y}, ${box.width}x${box.height}) Hash: <code>0x${(box.embedding_hash || 0).toString(16)}</code></span>
              <button class="btn-compact-face-match" data-hash="${box.embedding_hash || 0}" style="padding: 2px 6px; font-size: 0.7rem; background:#ec4899; color:white; border:none; border-radius:3px; cursor:pointer;">
                🔍 Match Face
              </button>
            </div>
          `).join('')}
        </div>
        <div id="faceMatchResultContainer" style="margin-top:0.4rem; display:none; background:#0f172a; padding:6px; border-radius:4px; font-family:monospace; color:#38bdf8;"></div>
      </div>
      ` : ''}

      <div class="tag-cloud" style="margin-top:0.4rem;">
        ${rustPhoto.face_detection.face_tags.map((ft: string) => `<span class="tag-badge" style="background:#ec4899; color:#fff;">👤 ${ft}</span>`).join(' ')}
      </div>
    </div>
    ` : ''}

    <!-- SCHEMATIC TITLE BLOCK & ISOLATED OCR -->
    ${rustAnalyzer && rustAnalyzer.title_block && rustAnalyzer.title_block.found ? `
    <div class="data-card" style="border: 2px solid #f59e0b; background: rgba(245, 158, 11, 0.08);">
      <h4 style="color:#f59e0b;">📌 SCHEMATIC TITLE BLOCK (ISOLATED OCR)</h4>
      <table class="meta-table">
        <tr><th>Company / Brand</th><td><strong>${rustAnalyzer.title_block.company_brand}</strong></td></tr>
        <tr><th>Drawing Number</th><td><span style="font-family:monospace; background:#f59e0b; color:#0f172a; padding:1px 6px; border-radius:3px; font-weight:700;">${rustAnalyzer.title_block.drawing_number}</span></td></tr>
        <tr><th>Title Block Box</th><td>(${rustAnalyzer.title_block.x}, ${rustAnalyzer.title_block.y}) ${rustAnalyzer.title_block.width}x${rustAnalyzer.title_block.height} px</td></tr>
      </table>
      <div style="margin-top:0.4rem; font-size:0.75rem; color:#cbd5e1;">
        <strong>Title Block Text OCR:</strong>
        <div class="json-view" style="margin-top:2px; color:#fef08a; font-weight:600;">${rustAnalyzer.title_block.title_text_extracted}</div>
      </div>
    </div>
    ` : ''}

    <!-- IMAGE ANALYSIS & VISUAL TAGS -->
    ${rustAnalyzer ? `
    <div class="data-card">
      <h4>🎨 IMAGE TAGS & VISUAL METRICS</h4>
      <table class="meta-table">
        <tr><th>Dimensions</th><td>${rustAnalyzer.width} x ${rustAnalyzer.height} px (${rustAnalyzer.aspect_ratio.toFixed(2)})</td></tr>
        <tr><th>Schematic Lines</th><td><strong>${rustAnalyzer.lines_detected ? rustAnalyzer.lines_detected.length : 0} line trace(s)</strong></td></tr>
        <tr><th>Mean RGB</th><td>R:${rustAnalyzer.mean_red.toFixed(1)}, G:${rustAnalyzer.mean_green.toFixed(1)}, B:${rustAnalyzer.mean_blue.toFixed(1)}</td></tr>
        <tr><th>Luminance & Contrast</th><td>Luma: ${rustAnalyzer.luminance.toFixed(1)}, Contrast StdDev: ${rustAnalyzer.contrast.toFixed(2)}</td></tr>
        <tr><th>Perceptual dHash</th><td><code>${rustAnalyzer.dhash_hex}</code></td></tr>
      </table>
    </div>
    ` : ''}

    <!-- DOCX / WORD DOCUMENT CONTENT EXTRACTION -->
    ${rustDocx ? `
    <div class="data-card" style="border: 2px solid #38bdf8; background: rgba(56, 189, 248, 0.08);">
      <h4 style="color:#38bdf8;">📄 MICROSOFT WORD (.DOCX / .DOC) EXTRACTOR</h4>
      <table class="meta-table">
        <tr><th>Format Type</th><td><strong>${rustDocx.format_type}</strong></td></tr>
        <tr><th>Word Count</th><td><span style="font-weight:700; color:#38bdf8;">${rustDocx.word_count} words</span></td></tr>
        <tr><th>Paragraphs</th><td>${rustDocx.paragraph_count} paragraph(s)</td></tr>
        ${rustDocx.author ? `<tr><th>Author</th><td>${rustDocx.author}</td></tr>` : ''}
        ${rustDocx.title ? `<tr><th>Document Title</th><td>${rustDocx.title}</td></tr>` : ''}
      </table>
      <div style="margin-top:0.4rem; font-size:0.75rem; color:#cbd5e1;">
        <strong>Document OpenXML Text Snippet:</strong>
        <div class="json-view" style="margin-top:2px; color:#e2e8f0; font-weight:600; max-height:120px;">${rustDocx.extracted_text_snippet || 'No text extracted.'}</div>
      </div>
      <div class="tag-cloud" style="margin-top:0.4rem;">
        ${rustDocx.docx_tags.map((t: string) => `<span class="tag-badge" style="background:#0284c7; color:#fff;">📄 ${t}</span>`).join(' ')}
      </div>
    </div>
    ` : ''}

    <!-- OCR EXTRACTED TEXT -->
    ${rustOcr ? `
    <div class="data-card">
      <h4>🔤 OCR TAGS & RECOGNIZED TEXT</h4>
      <div class="json-view" style="color:#e2e8f0; font-weight:600;">${rustOcr.extracted_text || 'No text detected.'}</div>
    </div>
    ` : ''}

    <!-- PHOTO IDENTIFIER -->
    ${rustPhoto ? `
    <div class="data-card">
      <h4>🏷️ PHOTO CLASSIFICATION & TRAITS</h4>
      <table class="meta-table">
        <tr><th>Category</th><td><strong>${rustPhoto.primary_category}</strong> (${(rustPhoto.confidence * 100).toFixed(0)}%)</td></tr>
        <tr><th>Palette Type</th><td>${rustPhoto.color_palette_type}</td></tr>
        <tr><th>Traits</th><td>${rustPhoto.detected_traits.join(', ')}</td></tr>
      </table>
    </div>
    ` : ''}

    <!-- SVG VECTOR CONVERSION -->
    ${rustSvg ? `
    <div class="data-card">
      <h4>📐 IMAGE TO SVG VECTOR GRAPHICS</h4>
      <table class="meta-table">
        <tr><th>SVG Paths</th><td>${rustSvg.path_count} paths</td></tr>
      </table>
      <div class="json-view" style="max-height:100px;">${escapeHTML(rustSvg.svg_xml.slice(0, 400))}...</div>
    </div>
    ` : ''}

    <!-- EXIF / METADATA -->
    <div class="data-card">
      <h4>🏷️ EXIF / METADATA & FILESYSTEM DETAILS</h4>
      <table class="meta-table">
        <tr><th>File Name</th><td>${fileItem.name}</td></tr>
        <tr><th>Path</th><td>${fileItem.relativePath}</td></tr>
        <tr><th>Size</th><td>${formatBytes(fileItem.size)}</td></tr>
        <tr><th>Type</th><td>${fileItem.type || 'Binary'}</td></tr>
      </table>
    </div>

    <!-- COMPLETE SIDECAR JSON -->
    <div class="data-card">
      <h4>📋 COMPLETE SIDECAR METADATA JSON</h4>
      <div class="json-view">${JSON.stringify({
        file_name: fileItem.name,
        relative_path: fileItem.relativePath,
        file_size: fileItem.size,
        sidecar: {
          FILE_TAGS: fileTags,
          OCR_TAGS: rustOcr ? rustOcr.extracted_text.split_whitespace().slice(0, 10) : [],
          IMAGE_TAGS: rustAnalyzer ? [rustAnalyzer.dhash_hex] : [],
          FACE_DETECTION: rustPhoto ? rustPhoto.face_detection : {},
          PHOTO_ID: rustPhoto ? rustPhoto.primary_category : "Unknown",
          EXIF: meta.exifTags || {}
        }
      }, null, 2)}</div>
    </div>
  `;

  // Attach PDF breakout listener
  document.getElementById('btnInspectorPdfBreakout')?.addEventListener('click', () => {
    openPdfBreakoutModal(fileItem, currentInspectedImgUrl);
  });

  // Attach sub-photo download and preview listeners
  masterInspectorContainer.querySelectorAll('.btn-download-subphoto').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const target = e.currentTarget as HTMLButtonElement;
      const dataUrl = target.getAttribute('data-url');
      const name = target.getAttribute('data-name');
      if (dataUrl && name) {
        downloadDataUrl(dataUrl, name);
      }
    });
  });

  masterInspectorContainer.querySelectorAll('.btn-preview-subphoto').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const target = e.currentTarget as HTMLButtonElement;
      const dataUrl = target.getAttribute('data-url');
      if (dataUrl) {
        imagePreviewContainer.innerHTML = `
          <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; gap:0.5rem; height:100%; width:100%;">
            <img src="${dataUrl}" style="max-width:100%; max-height:85%; object-fit:contain; border:2px solid var(--accent); border-radius:4px; box-shadow:0 0 15px rgba(56,189,248,0.4);" />
            <button id="btnResetMainPreview" class="btn primary" style="font-size:0.75rem; padding:0.25rem 0.6rem;">↺ Back to Full Document & Overlays</button>
          </div>
        `;
        document.getElementById('btnResetMainPreview')?.addEventListener('click', () => {
          renderVisualDocumentOverlays();
        });
      }
    });
  });

  // Attach face match listener
  masterInspectorContainer.querySelectorAll('.btn-compact-face-match').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const targetBtn = e.currentTarget as HTMLButtonElement;
      const targetHash = targetBtn.getAttribute('data-hash') || '0';
      const resultContainer = document.getElementById('faceMatchResultContainer');
      if (resultContainer) {
        resultContainer.style.display = 'block';
        resultContainer.innerHTML = '🔍 Querying Rust Facial Identification Engine...';
        try {
          const resp = await fetch('/api/face-match', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ hash1: parseInt(targetHash), hash2: parseInt(targetHash) })
          });
          const data = await resp.json();
          resultContainer.innerHTML = `✅ <strong>Face Identified!</strong> Match Confidence: <strong>${data.match_percentage}</strong> | Feature Hash: <code>${data.hash1}</code>`;
        } catch (err) {
          resultContainer.innerHTML = `❌ Face Matcher Error: ${err}`;
        }
      }
    });
  });
}

function downloadDataUrl(dataUrl: string, filename: string) {
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

async function generateMetaPhotos(
  fileItem: FileItem,
  rustAnalyzer: any,
  rustPhoto: any,
  rustOcr: any
): Promise<Array<{ id: string; title: string; dataUrl: string; width: number; height: number; x: number; y: number }>> {
  return new Promise((resolve) => {
    const img = new Image();
    const url = itemUrl(fileItem);
    img.onload = () => {
      const results: Array<{ id: string; title: string; dataUrl: string; width: number; height: number; x: number; y: number }> = [];
      const naturalW = img.naturalWidth || img.width;
      const naturalH = img.naturalHeight || img.height;

      function crop(x: number, y: number, w: number, h: number, title: string) {
        const cropX = Math.max(0, Math.min(naturalW - 1, Math.round(x)));
        const cropY = Math.max(0, Math.min(naturalH - 1, Math.round(y)));
        const cropW = Math.max(1, Math.min(naturalW - cropX, Math.round(w)));
        const cropH = Math.max(1, Math.min(naturalH - cropY, Math.round(h)));

        if (cropW < 5 || cropH < 5) return;

        const canvas = document.createElement('canvas');
        canvas.width = Math.min(cropW, 2000);
        canvas.height = Math.min(cropH, 2000);
        const ctx = canvas.getContext('2d');
        if (ctx) {
          ctx.drawImage(img, cropX, cropY, cropW, cropH, 0, 0, canvas.width, canvas.height);
          results.push({
            id: `meta_${results.length + 1}`,
            title,
            dataUrl: canvas.toDataURL('image/png'),
            width: cropW,
            height: cropH,
            x: cropX,
            y: cropY
          });
        }
      }

      // 1. Title Block Crop
      if (rustAnalyzer?.title_block?.found) {
        const tb = rustAnalyzer.title_block;
        crop(tb.x, tb.y, tb.width, tb.height, '📌 Title Block Crop');
      }

      // 2. Face Detection Crops
      const faceBoxes = rustPhoto?.face_detection?.face_boxes || [];
      faceBoxes.forEach((box: any, idx: number) => {
        crop(box.x, box.y, box.width, box.height, `👤 Face Crop #${idx + 1}`);
      });

      // 3. Top OCR / Text Region Crops
      const wordRegions = rustOcr?.word_regions || [];
      if (wordRegions.length > 0) {
        const significant = wordRegions.slice(0, 3);
        significant.forEach((w: any, idx: number) => {
          crop(w.x || 0, w.y || 0, w.width || 100, w.height || 40, `🔤 Text Crop #${idx + 1}: "${(w.text || '').slice(0, 12)}"`);
        });
      }

      // 4. Sub-Panel Quadrant Meta-Photos (Top-Left, Top-Right, Bottom-Left, Bottom-Right)
      const halfW = Math.floor(naturalW / 2);
      const halfH = Math.floor(naturalH / 2);
      if (halfW > 20 && halfH > 20) {
        crop(0, 0, halfW, halfH, '🎛️ Sub-Panel (Top-Left)');
        crop(halfW, 0, naturalW - halfW, halfH, '🎛️ Sub-Panel (Top-Right)');
        crop(0, halfH, halfW, naturalH - halfH, '🎛️ Sub-Panel (Bottom-Left)');
        crop(halfW, halfH, naturalW - halfW, naturalH - halfH, '🎛️ Sub-Panel (Bottom-Right)');
      }

      URL.revokeObjectURL(url);
      resolve(results);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve([]);
    };
    img.src = url;
  });
}

/** The traced SVG laid over the scan: the archive tracer's layered trace for a filed drawing (turned back onto the scan
 *  as it lies), else this file's own vector trace. */
function laySvgVector(where: HTMLElement, item: FileItem, ownSvg: string) {
  const layer = where.querySelector('.svg-vector-layer') as HTMLElement | null;
  const img = where.querySelector('#activeOverlayImage') as HTMLImageElement | null;
  if (!layer || !img) return;
  archiveTrace(item).then(t => {
    const svg = t?.svg || ownSvg;
    if (!svg) { layer.innerHTML = '<span class="svg-vector-note">No vector trace yet for this file.</span>'; return; }
    layer.innerHTML = svg;
    layer.classList.toggle('archive', !!t);
    const el = layer.querySelector('svg') as SVGSVGElement | null;
    if (!el) return;
    el.setAttribute('preserveAspectRatio', 'none');
    const rot = t?.rotate || 0, side = rot === 90 || rot === 270;
    const fit = () => {   // the upright trace, turned clockwise by its rotation, sits exactly on the scan
      const w = img.clientWidth, h = img.clientHeight, sw = side ? h : w, sh = side ? w : h;
      Object.assign(el.style, { position: 'absolute', width: sw + 'px', height: sh + 'px', left: (w - sw) / 2 + 'px',
        top: (h - sh) / 2 + 'px', transform: rot ? `rotate(${rot}deg)` : '', transformOrigin: '50% 50%' });
    };
    if (img.complete) fit(); else img.addEventListener('load', fit, { once: true });
    new ResizeObserver(fit).observe(img);
    const cad = t ? traceToCad(t.svg) : null;   // the CAD file this drawing's type asks for, made from the trace (traceCad.ts)
    if (cad) {
      const a = Object.assign(document.createElement('a'), {
        className: 'svg-vector-save', textContent: `⬇ ${cad.what}`, download: `${item.name.replace(/\.[^.]+$/, '')} (traced).${cad.ext}`,
        href: URL.createObjectURL(new Blob([cad.text], { type: cad.mime })), title: `Made from the trace of drawing ${cad.name}` });
      layer.parentElement?.appendChild(a);
    }
  });
}

function renderVisualDocumentOverlays() {
  if (!currentInspectedFileItem || !currentInspectedFileItem.isImage || !currentInspectedImgUrl) return;

  const ocrWords: any[] = currentInspectedOcrData?.word_regions || [];
  const faceBoxes: any[] = currentInspectedPhotoData?.face_detection?.face_boxes || [];

  // Create wrapper HTML
  const svgXml = currentInspectedSvgData?.svg_xml || '';
  const wrapperHTML = `
    <div class="ocr-overlay-wrapper" id="activeOverlayWrapper" style="position:relative; display:inline-block;">
      <img src="${currentInspectedImgUrl}" id="activeOverlayImage" alt="${currentInspectedFileItem.name}" />
      ${showSvgVector ? '<div class="svg-vector-layer"></div>' : ''}
      <div id="overlayLayerContainer"></div>
    </div>
  `;

  // Render to Left 1/3 Preview Container
  imagePreviewContainer.innerHTML = wrapperHTML;

  const imgEl = imagePreviewContainer.querySelector('#activeOverlayImage') as HTMLImageElement;
  const overlayContainer = imagePreviewContainer.querySelector('#overlayLayerContainer') as HTMLElement;

  function attachScaledOverlays() {
    if (!imgEl || !overlayContainer) return;
    const naturalW = imgEl.naturalWidth || 1;
    const naturalH = imgEl.naturalHeight || 1;
    const clientW = imgEl.clientWidth || naturalW;
    const clientH = imgEl.clientHeight || naturalH;

    const scaleX = clientW / naturalW;
    const scaleY = clientH / naturalH;

    let layerHTML = '';

    if (showOcrBoxes || showTextOverlay) {
      for (const w of ocrWords) {
        const sx = w.x * scaleX;
        const sy = w.y * scaleY;
        const sw = w.width * scaleX;
        const sh = w.height * scaleY;

        layerHTML += `
          <div class="ocr-overlay-box" style="
            left: ${sx}px;
            top: ${sy}px;
            width: ${sw}px;
            height: ${sh}px;
            display: ${showOcrBoxes ? 'block' : 'none'};
          " title="Word: '${escapeHTML(w.text)}' (Conf: ${(w.confidence * 100).toFixed(0)}%)">
            ${showTextOverlay ? `<span class="ocr-overlay-text">${escapeHTML(w.text)}</span>` : ''}
          </div>
        `;
      }
    }

    if (showFaceOverlay) {
      for (let idx = 0; idx < faceBoxes.length; idx++) {
        const f = faceBoxes[idx];
        const sx = f.x * scaleX;
        const sy = f.y * scaleY;
        const sw = f.width * scaleX;
        const sh = f.height * scaleY;

        layerHTML += `
          <div class="face-overlay-box" style="
            left: ${sx}px;
            top: ${sy}px;
            width: ${sw}px;
            height: ${sh}px;
          " title="Face #${idx+1}">
            <span class="face-overlay-tag">👤 Face #${idx+1}</span>
          </div>
        `;
      }
    }

    if (showSchematicLines) {
      const detectedLines: any[] = currentInspectedAnalyzerData?.lines_detected || [];
      for (const line of detectedLines) {
        const sx1 = line.x1 * scaleX;
        const sy1 = line.y1 * scaleY;
        const sx2 = line.x2 * scaleX;
        const sy2 = line.y2 * scaleY;

        const lw = Math.max(Math.abs(sx2 - sx1), 2);
        const lh = Math.max(Math.abs(sy2 - sy1), 2);

        layerHTML += `
          <div class="schematic-line-overlay" style="
            left: ${sx1}px;
            top: ${sy1}px;
            width: ${lw}px;
            height: ${lh}px;
          " title="Schematic Trace Line (${line.orientation}): ${line.length.toFixed(0)}px"></div>
        `;
      }
    }

    if (showTitleBlock) {
      const tb: any = currentInspectedAnalyzerData?.title_block;
      if (tb && tb.found) {
        const sx = tb.x * scaleX;
        const sy = tb.y * scaleY;
        const sw = tb.width * scaleX;
        const sh = tb.height * scaleY;

        layerHTML += `
          <div class="title-block-overlay" style="
            left: ${sx}px;
            top: ${sy}px;
            width: ${sw}px;
            height: ${sh}px;
          " title="Title Block: ${escapeHTML(tb.title_text_extracted)} | Dwg #: ${tb.drawing_number}">
            <span class="title-block-tag">📌 SCHEMATIC TITLE BLOCK (${tb.drawing_number})</span>
          </div>
        `;
      }
    }

    overlayContainer.innerHTML = layerHTML;
  }

  if (imgEl.complete) {
    attachScaledOverlays();
  } else {
    imgEl.onload = attachScaledOverlays;
  }
  if (showSvgVector) laySvgVector(imagePreviewContainer, currentInspectedFileItem, svgXml);

  // If Full Doc Modal is open, render to modal body as well
  if (fullDocModal.style.display === 'flex') {
    const modalTitle = document.getElementById('fullDocTitle');
    if (modalTitle) {
      modalTitle.innerText = `📄 Full Document: ${currentInspectedFileItem.name} (${ocrWords.length} text regions, ${faceBoxes.length} face regions)`;
    }
    fullDocModalBody.innerHTML = wrapperHTML;
    if (showSvgVector) laySvgVector(fullDocModalBody, currentInspectedFileItem, svgXml);
    const modalImgEl = fullDocModalBody.querySelector('#activeOverlayImage') as HTMLImageElement;
    const modalOverlayContainer = fullDocModalBody.querySelector('#overlayLayerContainer') as HTMLElement;
    if (modalImgEl) {
      const attachModalOverlays = () => {
        const nW = modalImgEl.naturalWidth || 1;
        const nH = modalImgEl.naturalHeight || 1;
        const cW = modalImgEl.clientWidth || nW;
        const cH = modalImgEl.clientHeight || nH;
        const sX = cW / nW;
        const sY = cH / nH;

        let mHTML = '';
        if (showOcrBoxes || showTextOverlay) {
          for (const w of ocrWords) {
            mHTML += `
              <div class="ocr-overlay-box" style="
                left: ${w.x * sX}px;
                top: ${w.y * sY}px;
                width: ${w.width * sX}px;
                height: ${w.height * sY}px;
                display: ${showOcrBoxes ? 'block' : 'none'};
              ">
                ${showTextOverlay ? `<span class="ocr-overlay-text">${escapeHTML(w.text)}</span>` : ''}
              </div>
            `;
          }
        }
        if (modalOverlayContainer) modalOverlayContainer.innerHTML = mHTML;
      };
      if (modalImgEl.complete) attachModalOverlays();
      else modalImgEl.onload = attachModalOverlays;
    }
  }
}

function pushRecentSlideshow(fileItem: FileItem) {
  if (recentVisitedFiles.some(f => f.relativePath === fileItem.relativePath)) {
    recentVisitedFiles = recentVisitedFiles.filter(f => f.relativePath !== fileItem.relativePath);
  }
  recentVisitedFiles.unshift(fileItem);
  if (recentVisitedFiles.length > 5) {
    recentVisitedFiles = recentVisitedFiles.slice(0, 5);
  }

  footerSlideshowTrack.innerHTML = '';
  for (const item of recentVisitedFiles) {
    const card = document.createElement('div');
    card.className = 'slideshow-item';
    const thumbUrl = item.isImage ? (item.thumbUrl ?? itemUrl(item)) : '';
    const thumbHTML = item.isImage ? `<img src="${thumbUrl}" class="slideshow-thumb" />` : `<span style="font-size:1.2rem;">📄</span>`;

    card.innerHTML = `
      ${thumbHTML}
      <div class="slideshow-meta">
        <div class="slideshow-name">${item.name}</div>
      </div>
    `;

    card.addEventListener('click', () => inspectFileItem(item));
    footerSlideshowTrack.appendChild(card);
  }
}

function extractFilenameTags(filename: string): string[] {
  return filename
    .replace(/\.[^/.]+$/, '')
    .split(/[^a-zA-Z0-9]+/)
    .filter(w => w.length >= 2)
    .map(w => w.toLowerCase());
}

function escapeHTML(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

async function runRustCategoryAndSortChartsUI() {
  try {
    const resp = await fetch('/api/catalog?sort=count');
    if (resp.ok) {
      const report = await resp.json();
      masterInspectorContainer.innerHTML = `
        <div class="data-card">
          <h4>🦀 RUST DATASET SORTING & CATEGORY CHARTS</h4>
          <div class="json-view" style="max-height:400px;">${JSON.stringify(report, null, 2)}</div>
        </div>
      `;
    }
  } catch (err) {
    console.warn("Rust API offline", err);
  }
}

function openPdfBreakoutModal(fileItem: FileItem, pdfUrl: string) {
  fullDocModal.style.display = 'flex';
  const modalTitle = document.getElementById('fullDocTitle');
  if (modalTitle) {
    modalTitle.innerHTML = `🚀 PDF Breakout Fullscreen Viewer: ${escapeHTML(fileItem.name)} (${formatBytes(fileItem.size)})`;
  }
  fullDocModalBody.innerHTML = `
    <div style="width:100%; height:100%; display:flex; flex-direction:column; background:#0f172a;">
      <iframe src="${pdfUrl}#toolbar=1&navpanes=1" style="width:100%; height:100%; border:none; background:#525659;" title="PDF Breakout Modal Frame"></iframe>
    </div>
  `;
}

function openDocumentBreakoutModal(fileItem: FileItem, pages: ExtractedImagePage[]) {
  fullDocModal.style.display = 'flex';
  const modalTitle = document.getElementById('fullDocTitle');
  if (modalTitle) {
    modalTitle.innerHTML = `🚀 Document Breakout Gallery (${pages.length} Images/Pages): ${escapeHTML(fileItem.name)}`;
  }
  fullDocModalBody.innerHTML = `
    <div style="width:100%; height:100%; overflow-y:auto; padding:1rem; display:flex; flex-direction:column; gap:1rem; align-items:center; background:#020617;">
      ${pages.map(p => `
        <div style="background:#0f172a; border:1px solid var(--border-color); padding:0.5rem; border-radius:6px; max-width:90%; text-align:center; box-shadow:0 8px 20px rgba(0,0,0,0.5);">
          <div style="font-size:0.8rem; color:#38bdf8; font-weight:700; margin-bottom:0.4rem;">${escapeHTML(p.title)} (${p.width}x${p.height} px)</div>
          <img src="${p.dataUrl}" style="max-width:100%; height:auto; border-radius:3px;" />
        </div>
      `).join('')}
    </div>
  `;
}


/** The archive's own extractors on this file: OCR, title block, rotation, dates, modules named, sections, Drive copy. */
async function showArchiveFacts(fileItem: FileItem) {
  const box = document.getElementById('archiveFacts');
  if (!box) return;
  const rel = fileItem.relativePath.startsWith('2026/') ? fileItem.relativePath.slice(5) : '';
  if (!rel) { box.innerHTML = '<div class="empty-state">Not an archive file: use the 🔬 Scanner to run the archive\'s extractors on it.</div>'; return; }
  box.innerHTML = '<div class="empty-state">Asking the archive\'s extractors…</div>';
  try {
    const f = await (await fetch('/api/file?path=' + encodeURIComponent(rel))).json();
    if (!f.filed) { box.innerHTML = '<div class="empty-state">The archive has no record of this file.</div>'; return; }
    const wy = (y: number | null) => (y ? `${y}|${y - 1967}` : '19xx');
    const esc = escapeHTML;
    const tb = (f.title_blocks || [])[0];
    const row = (k: string, v: string) => v ? `<tr><th>${k}</th><td>${v}</td></tr>` : '';
    box.innerHTML = `<div class="panel-header"><h2>🗃️ The archive's extractors on this file</h2></div><table class="meta-table">
      ${row('Filed as', esc(f.dest))}
      ${row('Year', `${wy(f.year)} <small>(${esc(f.year_source || '')})</small>`)}
      ${row('Models', (f.models || []).map((m: any) => `<a href="/archive/PAGES/${encodeURIComponent(m.code)}.html" target="_blank">${esc(m.code)}</a> ${esc(m.name || '')} · ${wy(m.year)}`).join('<br>'))}
      ${row('Google Drive', f.drive ? `<a href="${f.drive.view}" target="_blank" rel="noopener">open on Drive</a> · ${f.drive.public ? 'public' : 'private (sign in)'} · matched by ${esc(f.drive.how)}` : 'no Drive copy')}
      ${row('Title block', tb ? esc([tb.number, tb.dtype_name, tb.title, tb.date, tb.drawn && 'drawn ' + tb.drawn, tb.checked && 'checked ' + tb.checked, tb.issue && 'issue ' + tb.issue].filter(Boolean).join(' · ')) : '')}
      ${row('Rotation', f.rotation ? esc(f.rotation.verdict) + (f.rotation.rotate ? ` (${f.rotation.rotate}°)` : '') : '')}
      ${row('Dates in it', (f.dates || []).slice(0, 6).map((d: any) => `${wy(d.year)} <small>${esc(d.raw)}</small>`).join(' · '))}
      ${row('Modules named', [...new Set((f.modules_named || []).map((m: any) => m.code))].map(c => `<a href="/archive/PAGES/${encodeURIComponent(String(c))}.html" target="_blank">${esc(String(c))}</a>`).join(' '))}
      ${row('Hover links', (f.hover_boxes || []).length ? `word positions on ${(f.hover_boxes || []).length} page(s)` : '')}
      ${row('Manual sections', (f.sections || []).map((s: any) => esc(s.heading)).join(' · '))}
      ${row('Parts list', (f.parts_list || []).length ? `${f.parts_list.length} rows` : '')}
      ${row('Text', (f.pages || []).length ? `${f.pages.length} page(s), ${f.pages.filter((p: any) => p.method === 'ocr').length} read by OCR` : '')}
    </table>`;
  } catch (e) {
    box.innerHTML = `<div class="empty-state">The archive's extractors are not reachable (${escapeHTML(String(e))}). Start the suite with npm run dev.</div>`;
  }
}
