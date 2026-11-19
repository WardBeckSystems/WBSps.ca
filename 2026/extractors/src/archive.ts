import { FileItem } from './types';

// The 2026 archive is served at /archive/ by the dev server (see vite.config.ts)
export const ARCHIVE_BASE = '/archive/';

/** URL to display a file: archive items are served directly, picked files get a blob URL. */
export function itemUrl(item: FileItem): string {
  return item.url ?? URL.createObjectURL(item.file!);
}

/** The file's bytes; archive items are fetched once and kept. */
export async function itemFile(item: FileItem): Promise<File> {
  if (!item.file) {
    const blob = await (await fetch(item.url!)).blob();
    item.file = new File([blob], item.name, { type: blob.type });
  }
  return item.file;
}
