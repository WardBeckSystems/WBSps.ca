export interface FileItem {
  file?: File;            // picked files; archive items fetch theirs on demand
  url?: string;           // archive items: served from /archive/
  thumbUrl?: string;      // archive items: prebuilt JPEG thumbnail
  archive?: ArchiveInfo;
  relativePath: string;
  name: string;
  size: number;
  type: string;
  isImage: boolean;
  ocrText?: string;
  isManual?: boolean;
  specialFlag?: string;
  emojiBadge?: string;
  exifTagsCount?: number;
  metadata?: ImageMetadata;
}

export interface ArchiveInfo {
  model: string;
  year: number | null;
  section: string;
  category: string;
  note?: string;
  original: string;
}

/** One record of 2026/_catalog/catalog.json (written by Engineering/_tools/make_catalog.py) */
export interface ArchiveRecord {
  p: string; n: string; k: string; s: number; sec: string; cat: string; m: string;
  y: number | null; o: string; note: string; t: string; x: string;
}

export interface TreeNode {
  name: string;
  path: string;
  isDir: boolean;
  fileItem?: FileItem;
  children: Map<string, TreeNode>;
  size: number;
  hasManuals?: boolean;
}

export interface ImageMetadata {
  fileName: string;
  fileSize: number;
  mimeType: string;
  isManual?: boolean;
  specialFlag?: string;
  cameraModel?: string;
  dateTaken?: string;
  gpsCoords?: { lat: any; lon: any };
  dimensions?: { width: number; height: number; aspectRatio: string };
  exifTags?: Record<string, string | number | boolean>;
  rawHeaders?: Record<string, any>;
}

export interface BatchEXIFSummary {
  totalFiles: number;
  totalImages?: number;
  processedCount: number;
  exifCount: number;
  geotaggedCount: number;
  imagesWithEXIF?: number;
  cameras: Record<string, number>;
  locations?: Array<{ lat: any; lon: any; camera?: string; fileName?: string; name?: string; path?: string }>;
  geotaggedFiles: Array<{ lat: any; lon: any; camera?: string; fileName?: string; name?: string; path?: string }>;
  dateRange: { earliest?: string; latest?: string };
  dateRanges?: { earliest?: string; latest?: string };
}
