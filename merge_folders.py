#!/usr/bin/env python3
"""
Folder Combiner Script
Merges all 35 split directories (WBSps.ca-20260906T145600Z-1-*) into the unified WBSps.ca directory.
"""

import os
import sys
import shutil
import glob
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
TARGET_DIR = BASE_DIR / "WBSps.ca"

def merge_directories():
    split_dirs = sorted(glob.glob(str(BASE_DIR / "WBSps.ca-20260906T145600Z-1-*")))
    print(f"Found {len(split_dirs)} split folders to merge into {TARGET_DIR.name}...")

    TARGET_DIR.mkdir(exist_ok=True)

    moved_files = 0
    skipped_files = 0
    merged_dirs = 0

    for idx, s_dir in enumerate(split_dirs, 1):
        s_path = Path(s_dir)
        source_sub = s_path / "WBSps.ca"
        
        # If there's a subfolder WBSps.ca, merge from there; otherwise merge directly from s_path
        src_root = source_sub if source_sub.exists() else s_path

        print(f"[{idx}/{len(split_dirs)}] Merging: {s_path.name}...")

        for root, dirs, files in os.walk(src_root):
            rel_path = Path(root).relative_to(src_root)
            dest_dir = TARGET_DIR / rel_path
            dest_dir.mkdir(parents=True, exist_ok=True)

            for f in files:
                src_file = Path(root) / f
                dest_file = dest_dir / f

                if not dest_file.exists():
                    shutil.move(str(src_file), str(dest_file))
                    moved_files += 1
                else:
                    # If sizes match, skip duplicate; if destination is smaller, replace
                    if src_file.stat().st_size > dest_file.stat().st_size:
                        shutil.move(str(src_file), str(dest_file))
                        moved_files += 1
                    else:
                        src_file.unlink()
                        skipped_files += 1

        merged_dirs += 1
        # Remove empty split directory
        shutil.rmtree(s_path, ignore_errors=True)

    print("\n=======================================================")
    print(f" Successfully merged {merged_dirs} split directories!")
    print(f"   • Total Files Moved/Merged : {moved_files}")
    print(f"   • Duplicate Files Handled  : {skipped_files}")
    print(f"   • Destination Master Path  : {TARGET_DIR}")
    print("=======================================================\n")

if __name__ == "__main__":
    merge_directories()
