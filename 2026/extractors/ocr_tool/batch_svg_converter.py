#!/usr/bin/env sys.executable
import sys
import os
import time
from pathlib import Path
import vtracer

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tif', '.tiff'}

def convert_single_image_to_svg(image_path: Path) -> str:
    svg_path = image_path.with_suffix('.svg')
    
    # Skip if SVG already exists and is non-empty
    if svg_path.exists() and svg_path.stat().st_size > 0:
        return "cached"

    try:
        vtracer.convert_image_to_svg_py(
            str(image_path),
            str(svg_path),
            colormode='color',
            hierarchical='stacked',
            mode='spline',
            filter_speckle=4,
            color_precision=6,
            layer_difference=16,
            corner_threshold=60,
            length_threshold=4.0,
            max_iterations=10,
            splice_threshold=45,
            path_precision=3
        )
        return "created"
    except Exception as e:
        return f"error: {e}"

def run_batch_svg_conversion(target_dir: str):
    root = Path(target_dir)
    if not root.exists():
        print(f"Error: Target path '{target_dir}' does not exist.")
        return

    print("==================================================")
    print("📐 High-Performance Batch Raster-to-SVG Vectorizer (Rust vtracer)")
    print(f"Target Directory: {root.resolve()}")
    print("==================================================")

    images = [
        p for p in root.rglob('*')
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS and not p.name.endswith('.json')
    ]
    print(f"Found {len(images)} raster images to trace into SVG vectors.")

    created = 0
    cached = 0
    errors = 0
    start_time = time.time()

    for i, img_path in enumerate(images, 1):
        status = convert_single_image_to_svg(img_path)
        if status == "created":
            created += 1
            if created % 50 == 0 or created == 1:
                print(f"[{i}/{len(images)}] 📐 [SVG Created] {img_path.name}.svg")
        elif status == "cached":
            cached += 1
            if i % 2500 == 0 or i == len(images):
                print(f"[{i}/{len(images)}] ⏩ [Cached SVG] {cached} vectors up-to-date")
        else:
            errors += 1
            print(f"[{i}/{len(images)}] ❌ {img_path.name}: {status}")

    elapsed = time.time() - start_time
    print("\n==========================================")
    print("BATCH RASTER-TO-SVG VECTORIZATION COMPLETE")
    print(f"Total Raster Images : {len(images)}")
    print(f"SVG Vectors Created : {created}")
    print(f"SVG Vectors Cached  : {cached}")
    print(f"Errors              : {errors}")
    print(f"Total Processing Time: {elapsed:.2f} seconds")
    print("==========================================")

if __name__ == '__main__':
    target = sys.argv[1] if len(sys.argv) > 1 else "../../WBSps.ca"
    run_batch_svg_conversion(target)
