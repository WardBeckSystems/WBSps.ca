#!/usr/bin/env sys.executable
import sys
import os
import time
import subprocess
from pathlib import Path

def run_master_pipeline():
    project_root = Path("/home/anthony/Documents/GitProjects/WBSps.ca")
    dataset_dir = project_root / "WBSps.ca"
    ocr_tool_dir = project_root / "public/extractors/ocr_tool"
    python_bin = ocr_tool_dir / "venv/bin/python"
    rust_analyzer_bin = project_root / "public/extractors/rust_analyzer/target/release/rust_analyzer"

    print("==================================================================")
    print("🚀 MASTER RELENTLESS PIPELINE RUNNER: PROCESS ALL DATASET & GO")
    print(f"Dataset Target Path: {dataset_dir.resolve()}")
    print("==================================================================")

    start_time = time.time()

    # Step 1: Run Rust Analyzer & Sorter on all 52,366 files
    print("\n[Step 1/4] 🦀 Executing High-Performance Rust Analyzer & Sorter...")
    try:
        res = subprocess.run([str(rust_analyzer_bin), str(dataset_dir)], capture_output=True, text=True)
        print(res.stdout.strip())
    except Exception as e:
        print(f"Error executing Rust Analyzer: {e}")

    # Step 2: Run Universal Sidecar Generator (.exif.json & .meta.json)
    print("\n[Step 2/4] 📄 Running Universal Sidecar Generator (.exif.json & .meta.json)...")
    try:
        sidecar_script = ocr_tool_dir / "sidecar_generator.py"
        res = subprocess.run([str(python_bin), str(sidecar_script), str(dataset_dir)], capture_output=True, text=True)
        print(res.stdout.strip()[-500:])
    except Exception as e:
        print(f"Error running Sidecar Generator: {e}")

    # Step 3: Run Relentless OCR Engine (.ocr.json)
    print("\n[Step 3/4] 🔥 Launching Relentless Batch OCR Engine...")
    try:
        ocr_script = ocr_tool_dir / "relentless_ocr.py"
        res = subprocess.run([str(python_bin), str(ocr_script), str(dataset_dir)], capture_output=True, text=True)
        print(res.stdout.strip()[-500:])
    except Exception as e:
        print(f"Error running OCR Engine: {e}")

    # Step 4: Run Batch Raster-to-SVG Vectorizer (.svg)
    print("\n[Step 4/4] 📐 Launching Batch Raster-to-SVG Vectorizer (vtracer)...")
    try:
        svg_script = ocr_tool_dir / "batch_svg_converter.py"
        res = subprocess.run([str(python_bin), str(svg_script), str(dataset_dir)], capture_output=True, text=True)
        print(res.stdout.strip()[-500:])
    except Exception as e:
        print(f"Error running SVG Vectorizer: {e}")

    elapsed = time.time() - start_time
    print("\n==================================================================")
    print("🎉 ALL PIPELINE TASKS COMPLETED RELENTLESSLY ACROSS ENTIRE DATASET!")
    print(f"Total Pipeline Execution Time: {elapsed:.2f} seconds")
    print("==================================================================")

if __name__ == '__main__':
    run_master_pipeline()
