#!/usr/bin/env python3
"""
Python Master Orchestrator for Rust Image Processing & Data Suite
Generates test dataset & images, compiles Rust code if needed, and executes full suite.
"""

import os
import sys
import json
import subprocess
from pathlib import Path

# Try importing PIL for synthetic image creation, otherwise create raw PPM/BMP images
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

PROJECT_DIR = Path(__file__).parent.resolve()
RUST_DIR = PROJECT_DIR / "rust_image_data_suite"
TARGET_BIN = RUST_DIR / "target" / "release" / "rust_image_data_suite"

def create_sample_text_data():
    sample_text_path = RUST_DIR / "data_samples.txt"
    text_content = """
Antigravity High Performance Rust Sorting Suite and Data Analyzer
Image Processing OCR Vectorization Photo Identification
QuickSort MergeSort HeapSort RadixSort InsertionSort TimSort Algorithm Benchmarks
Data analysis dataset sample names AeroMind CyberPulse OmniGrid VeriFlow SynWave NovaLogic ZentCraft
Efficiency comparison execution time nanoseconds comparisons swaps sorting verification complete.
    """.strip()
    with open(sample_text_path, "w", encoding="utf-8") as f:
        f.write(text_content)
    print(f"[Python] Created sample text dataset at: {sample_text_path}")
    return sample_text_path

def create_sample_image():
    img_path = RUST_DIR / "test_image.png"
    if HAS_PIL:
        # Create synthetic document image with text & geometric patterns
        img = Image.new("RGB", (400, 200), color=(245, 245, 240))
        draw = ImageDraw.Draw(img)
        
        # Add high-contrast text shapes
        draw.text((20, 20), "RUST OCR TEST 2026", fill=(10, 10, 10))
        draw.text((20, 60), "QuickSort MergeSort HeapSort", fill=(20, 20, 100))
        draw.text((20, 100), "Image Analyzer Photo ID SVG", fill=(150, 20, 20))
        
        # Add some geometric shapes / line art
        draw.rectangle([300, 20, 380, 100], outline=(0, 128, 0), width=3)
        draw.ellipse([300, 110, 380, 180], fill=(200, 100, 50))
        
        img.save(img_path)
        print(f"[Python] Created synthetic PIL image at: {img_path}")
    else:
        # Fallback to PPM binary format converting to simple P6
        ppm_path = RUST_DIR / "test_image.ppm"
        width, height = 200, 100
        header = f"P6\n{width} {height}\n255\n".encode("ascii")
        pixels = bytearray()
        for y in range(height):
            for x in range(width):
                pixels.extend([(x * 2) % 256, (y * 2) % 256, (x + y) % 256])
        with open(ppm_path, "wb") as f:
            f.write(header + pixels)
        img_path = ppm_path
        print(f"[Python] Created fallback PPM image at: {img_path}")
    return img_path

def run_rust_pipeline(img_path, text_path):
    output_json = RUST_DIR / "report_output.json"
    
    print("\n=======================================================")
    print("      KICKING OFF RUST IMAGE & DATA SUITE             ")
    print("=======================================================\n")
    
    cmd = [
        str(TARGET_BIN),
        "run-all",
        "--image", str(img_path),
        "--text-file", str(text_path),
        "--output-json", str(output_json)
    ]
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error running Rust binary:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")
        sys.exit(1)
        
    print(res.stdout)
    
    if output_json.exists():
        with open(output_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        display_summary_report(data)

def display_summary_report(data):
    print("\n" + "="*70)
    print("                RUST DATA SUITE FINAL REPORT           ")
    print("="*70)
    
    # 1. OCR
    ocr = data.get("ocr_result", {})
    print(f"\n📷 1. OCR TOOL RESULTS:")
    print(f"   • Extracted Text Preview : {ocr.get('extracted_text', '')[:80]}...")
    print(f"   • Lines Detected          : {ocr.get('line_count')}")
    print(f"   • Words Extracted        : {ocr.get('word_count')}")
    print(f"   • Glyph Bounding Boxes   : {len(ocr.get('detected_characters', []))}")
    
    # 2. Image Analyzer
    img_an = data.get("image_analysis", {})
    print(f"\n📊 2. IMAGE ANALYZER:")
    print(f"   • Dimensions             : {img_an.get('width')} x {img_an.get('height')} px")
    print(f"   • Aspect Ratio           : {img_an.get('aspect_ratio'):.2f}")
    print(f"   • Mean RGB Color         : R:{img_an.get('mean_red'):.1f}, G:{img_an.get('mean_green'):.1f}, B:{img_an.get('mean_blue'):.1f}")
    print(f"   • Contrast / StdDev      : {img_an.get('contrast'):.2f}")
    print(f"   • Perceptual dHash       : {img_an.get('dhash_hex')}")
    
    # 3. Vectorizer (Image to SVG)
    svg = data.get("svg_vectorization", {})
    print(f"\n🎨 3. IMAGE TO SVG CONVERTER:")
    print(f"   • Output Canvas Size     : {svg.get('width')} x {svg.get('height')}")
    print(f"   • SVG Vector Path Count  : {svg.get('path_count')}")

    # 4. Photo Identifier
    photo = data.get("photo_identification", {})
    print(f"\n🔍 4. PHOTO IDENTIFIER:")
    print(f"   • Primary Category       : {photo.get('primary_category')} (Confidence: {photo.get('confidence') * 100:.1f}%)")
    print(f"   • Color Palette Type     : {photo.get('color_palette_type')}")
    print(f"   • Detected Traits        : {', '.join(photo.get('detected_traits', []))}")
    
    # 5. Word & Name Analyzer
    word = data.get("word_analysis", {})
    print(f"\n🔤 5. WORD & NAME ANALYZER:")
    print(f"   • Total Words Analyzed   : {word.get('total_words')}")
    print(f"   • Unique Vocabulary      : {word.get('unique_words')}")
    print(f"   • Avg Word Length        : {word.get('average_word_length'):.2f} chars")
    print(f"   • Generated Name Brands  : {', '.join(word.get('generated_word_names', [])[:6])}")
    
    # 6. Sorting Algorithm Benchmarks
    sorts = data.get("sorting_benchmarks", [])
    print(f"\n⚡ 6. RUST SORTING ALGORITHMS BENCHMARK REPORT:")
    print(f"   {'Algorithm':<24} | {'Elapsed Time':<14} | {'Comparisons':<12} | {'Swaps/Moves':<12} | {'Verified'}")
    print("   " + "-"*75)
    for s in sorts:
        time_str = f"{s['elapsed_nanos'] / 1000.0:.2f} µs" if s['elapsed_nanos'] > 1000 else f"{s['elapsed_nanos']} ns"
        verif = "YES ✅" if s['sorted_correctly'] else "NO ❌"
        print(f"   {s['algorithm']:<24} | {time_str:<14} | {s['comparisons']:<12} | {s['swaps']:<12} | {verif}")
    print("\n" + "="*70 + "\n")

import socket
import time
import webbrowser

def ensure_rust_bin():
    if not TARGET_BIN.exists():
        print(f"[Python] Compiling Rust release binary at {RUST_DIR}...")
        res = subprocess.run(["cargo", "build", "--release"], cwd=RUST_DIR)
        if res.returncode != 0:
            print("Error: Failed to compile Rust binary.")
            sys.exit(1)

def launch_web_interface():
    port = int(os.environ.get("RUST_PORT", 26303))
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    url = f"http://127.0.0.1:{port}"
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    is_running = (sock.connect_ex(('127.0.0.1', port)) == 0)
    sock.close()

    if not is_running:
        static_dir = PROJECT_DIR / "public" / "extractors" / "dist"
        print(f"\n🚀 Starting Rust Micro-API Server on {url} (Dashboard: {static_dir})...")
        cmd = [str(TARGET_BIN), "serve", "--port", str(port), "--static-dir", str(static_dir)]
        subprocess.Popen(cmd, start_new_session=True)
        time.sleep(1.0)
    else:
        print(f"\n🌐 Rust Micro-API Server is active on {url}")

    print(f"🌐 Opening web application in default browser: {url}")
    webbrowser.open(url)

if __name__ == "__main__":
    ensure_rust_bin()
    text_path = create_sample_text_data()
    img_path = create_sample_image()
    run_rust_pipeline(img_path, text_path)
    launch_web_interface()

