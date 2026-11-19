#!/usr/bin/env sys.executable
import sys
import os
import json
import time
from pathlib import Path
from PIL import Image, ExifTags
from concurrent.futures import ThreadPoolExecutor, as_completed

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tif', '.tiff'}

def extract_human_exif(img: Image.Image) -> dict:
    exif_dict = {}
    try:
        raw_exif = img._getexif() if hasattr(img, '_getexif') else None
        if raw_exif:
            for tag_id, value in raw_exif.items():
                tag_name = ExifTags.TAGS.get(tag_id, f"Tag_{tag_id}")
                if isinstance(value, bytes):
                    try:
                        value = value.decode('utf-8', errors='ignore').strip('\x00')
                    except Exception:
                        value = str(value)
                elif isinstance(value, tuple):
                    value = [str(v) for v in value]
                exif_dict[tag_name] = str(value)
    except Exception:
        pass
    return exif_dict

def extract_word_tokens(name: str) -> list:
    return [w.lower() for w in name.replace('.', ' ').replace('_', ' ').replace('-', ' ').split() if len(w) > 1]

def is_sidecar_up_to_date(source_path: Path, sidecar_path: Path) -> bool:
    if not sidecar_path.exists():
        return False
    try:
        sidecar_stat = sidecar_path.stat()
        source_stat = source_path.stat()
        return sidecar_stat.st_size > 0 and sidecar_stat.st_mtime >= source_stat.st_mtime
    except Exception:
        return False

def process_single_file(path: Path) -> str:
    if path.name.endswith('.json') or path.name.endswith('.ocr.json') or path.name.endswith('.exif.json') or path.name.endswith('.meta.json'):
        return "skip"

    ext = path.suffix.lower()
    is_manual = "manual" in path.name.lower() or "manuals" in path.name.lower()
    special_flag = "MANUAL_DOCUMENT" if is_manual else None

    try:
        stat = path.stat()
        file_info = {
            "filename": path.name,
            "relative_path": str(path),
            "extension": ext,
            "size_bytes": stat.st_size,
            "modified_time": time.ctime(stat.st_mtime),
            "is_manual": is_manual,
            "special_flag": special_flag,
            "word_tokens": extract_word_tokens(path.stem)
        }

        if ext in IMAGE_EXTENSIONS:
            exif_sidecar_path = path.with_suffix(path.suffix + '.exif.json')
            
            if is_sidecar_up_to_date(path, exif_sidecar_path):
                # Ensure existing sidecar updated if missing is_manual flag
                try:
                    with open(exif_sidecar_path, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                    if "is_manual" not in existing or existing["is_manual"] != is_manual:
                        existing["is_manual"] = is_manual
                        existing["special_flag"] = special_flag
                        with open(exif_sidecar_path, 'w', encoding='utf-8') as f:
                            json.dump(existing, f, indent=2)
                except Exception:
                    pass
                return "up_to_date"

            try:
                with Image.open(path) as img:
                    exif_tags = extract_human_exif(img)
                    file_info["width"] = img.size[0]
                    file_info["height"] = img.size[1]
                    file_info["format"] = img.format
                    file_info["mode"] = img.mode
                    file_info["exif"] = exif_tags

                with open(exif_sidecar_path, 'w', encoding='utf-8') as f:
                    json.dump(file_info, f, indent=2)
            except Exception as e:
                file_info["image_error"] = str(e)
                with open(exif_sidecar_path, 'w', encoding='utf-8') as f:
                    json.dump(file_info, f, indent=2)
        else:
            meta_sidecar_path = path.with_suffix(path.suffix + '.meta.json')
            
            if is_sidecar_up_to_date(path, meta_sidecar_path):
                try:
                    with open(meta_sidecar_path, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                    if "is_manual" not in existing or existing["is_manual"] != is_manual:
                        existing["is_manual"] = is_manual
                        existing["special_flag"] = special_flag
                        with open(meta_sidecar_path, 'w', encoding='utf-8') as f:
                            json.dump(existing, f, indent=2)
                except Exception:
                    pass
                return "up_to_date"

            with open(meta_sidecar_path, 'w', encoding='utf-8') as f:
                json.dump(file_info, f, indent=2)

        return "created"
    except Exception:
        return "error"

def generate_all_sidecars(target_directory: str):
    root = Path(target_directory)
    if not root.exists():
        print(f"Error: Target path '{target_directory}' does not exist.")
        return

    print("==================================================")
    print("🚀 Smart Sidecar Generator (With MANUAL_DOCUMENT Special Flag)")
    print(f"Target Directory: {root.resolve()}")
    print("==================================================")

    print("Scanning directory tree for all files...")
    all_files = [
        p for p in root.rglob('*')
        if p.is_file() and not (p.name.endswith('.json') or p.name.endswith('.ocr.json') or p.name.endswith('.exif.json') or p.name.endswith('.meta.json'))
    ]
    print(f"Found {len(all_files)} target source files.")

    created = 0
    up_to_date = 0
    errors = 0
    manual_count = 0

    start_time = time.time()

    with ThreadPoolExecutor(max_workers=16) as executor:
        futures = {executor.submit(process_single_file, p): p for p in all_files}
        for i, future in enumerate(as_completed(futures), 1):
            p = futures[future]
            if "manual" in p.name.lower():
                manual_count += 1
            res = future.result()
            if res == "created":
                created += 1
            elif res == "up_to_date":
                up_to_date += 1
            else:
                errors += 1

            if i % 5000 == 0 or i == len(all_files):
                elapsed = time.time() - start_time
                print(f"[{i}/{len(all_files)}] Processed... ({created} created, {up_to_date} cached, {manual_count} MANUAL flagged, {elapsed:.1f}s)", flush=True)

    print("\n==========================================")
    print("SMART SIDECAR GENERATION COMPLETE")
    print(f"Total Source Files    : {len(all_files)}")
    print(f"Manual Flagged Files  : {manual_count}")
    print(f"Sidecars Created      : {created}")
    print(f"Sidecars Up-To-Date   : {up_to_date}")
    print(f"Total Processing Time : {time.time() - start_time:.2f} seconds")
    print("==========================================")

if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else "../../WBSps.ca"
    generate_all_sidecars(target)
