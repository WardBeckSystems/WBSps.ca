#!/usr/bin/env sys.executable
import sys
import os
import json
from pathlib import Path
from PIL import Image, ExifTags

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tif', '.tiff'}

def extract_human_exif(img: Image.Image) -> dict:
    """
    Extract human-readable EXIF tags from PIL Image.
    """
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
    except Exception as e:
        print(f"  [EXIF parse notice]: {e}")
    return exif_dict

def process_file(path: Path, reader=None) -> dict:
    """
    Process a single image file and write sidecar files:
    - .exif.json (human-readable EXIF metadata)
    - .ocr.json (OCR transcript & combined metadata)
    """
    exif_sidecar_path = path.with_suffix(path.suffix + '.exif.json')
    ocr_sidecar_path = path.with_suffix(path.suffix + '.ocr.json')

    try:
        img = Image.open(path)
        exif_tags = extract_human_exif(img)

        # Write dedicated .exif.json sidecar file
        exif_data = {
            "filename": path.name,
            "relative_path": str(path),
            "width": img.size[0],
            "height": img.size[1],
            "format": img.format,
            "mode": img.mode,
            "exif": exif_tags
        }
        with open(exif_sidecar_path, 'w', encoding='utf-8') as f:
            json.dump(exif_data, f, indent=2)

        # Run OCR if reader available
        ocr_text = ""
        if reader:
            try:
                results = reader.readtext(str(path))
                detected_lines = [res[1] for res in results if res[1].strip()]
                ocr_text = "\n".join(detected_lines)
            except Exception as e:
                print(f"  [OCR Notice] {path.name}: {e}")

        # Write .ocr.json sidecar file
        ocr_data = {
            "filename": path.name,
            "relative_path": str(path),
            "width": img.size[0],
            "height": img.size[1],
            "format": img.format,
            "mode": img.mode,
            "exif": exif_tags,
            "ocr_text": ocr_text
        }
        with open(ocr_sidecar_path, 'w', encoding='utf-8') as f:
            json.dump(ocr_data, f, indent=2)

        print(f"✅ [Sidecars Created] {exif_sidecar_path.name} & {ocr_sidecar_path.name}")
        return {"file": str(path), "status": "created"}

    except Exception as e:
        print(f"❌ [Error] {path.name}: {e}")
        return {"file": str(path), "status": "error", "error": str(e)}

def run_batch_sidecar(target_path: str):
    path = Path(target_path)
    if not path.exists():
        print(f"Error: Target path '{target_path}' does not exist.")
        return

    print("==================================================")
    print(f"🔤 EXIF & OCR Sidecar (.exif.json & .ocr.json) Generator")
    print(f"Target Path: {path.resolve()}")
    print("==================================================")

    # Initialize EasyOCR engine
    reader = None
    try:
        import easyocr
        print("🚀 Initializing EasyOCR open-source engine...")
        reader = easyocr.Reader(['en'], gpu=False)
    except Exception as e:
        print(f"Notice: EasyOCR not available ({e}). Metadata EXIF sidecars will still be generated.")

    if path.is_file():
        process_file(path, reader)
    else:
        print("Scanning directory tree for image files...")
        image_files = [
            p for p in path.rglob('*')
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS and not p.name.endswith('.json')
        ]
        print(f"Found {len(image_files)} image files to process.")

        created_count = 0
        error_count = 0

        for i, img_path in enumerate(image_files, 1):
            print(f"[{i}/{len(image_files)}] ", end="", flush=True)
            res = process_file(img_path, reader)
            if res["status"] == "created":
                created_count += 1
            else:
                error_count += 1

        print("\n==========================================")
        print("BATCH EXIF & OCR SIDECAR GENERATION COMPLETE")
        print(f"Total Images Processed : {len(image_files)}")
        print(f"Sidecars Generated     : {created_count * 2}")
        print(f"Errors                 : {error_count}")
        print("==========================================")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        run_batch_sidecar(sys.argv[1])
    else:
        print("Usage: python3 ocr_extractor.py <folder_or_image_path>")
