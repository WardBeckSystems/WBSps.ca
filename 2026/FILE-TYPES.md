# File types and how to open them

Every file can be opened in the browser with `viewer.html?f=<path>` (links in the wiki, index and search do this). Formats a browser cannot show get a converted copy in `_previews/` (built by `timelines/make_previews.py`). The originals are never changed.

| Type | Files | What it is | Desktop application | Browser preview |
|---|---|---|---|---|
| `.md` | 17,277 | Markdown note / wiki page | Obsidian; VS Code; any text editor | shown as text |
| `.jpg` | 12,335 | photo / scan | any browser; Image Viewer; GIMP | native |
| `.dxf` | 10,263 | AutoCAD DXF drawing (footprints, panels) | LibreOffice Draw; Inkscape; KiCad (import) | SVG via ezdxf |
| `.svg` | 8,315 | vector drawing (renders, previews) | any browser; Inkscape | native |
| `.sample` | 5,362 | — | — | none |
| `.html` | 1,482 | — | — | none |
| `.kicad_sch` | 1,411 | KiCad schematic | KiCad | none |
| `.timestamp` | 1,262 | — | — | none |
| `.d` | 1,127 | — | — | none |
| `.kicad_sym` | 1,046 | — | — | none |
| `.rlib` | 886 | — | — | none |
| `.rmeta` | 876 | — | — | none |
| `.pdf` | 630 | PDF document | any browser; Document Viewer | native |
| `.png` | 530 | image | any browser; Image Viewer; GIMP | native |
| `.dwg` | 305 | AutoCAD DWG drawing (R11/R12 mechanical) | needs a DWG viewer — ODA File Converter or DraftSight (not installed) | none yet |
| `.docx` | 209 | Word document (modern manuals) | LibreOffice Writer | PDF via LibreOffice |
| `.yaml` | 110 | — | — | none |
| `.bak` | 107 | — | — | none |
| `.sch` | 95 | OrCAD SDT schematic (DOS) | OrCAD SDT (not installed) | none yet |
| `.jpeg` | 92 | photo / scan | any browser; Image Viewer; GIMP | native |
| `.so` | 81 | — | — | none |
| `.kicad_pcb` | 76 | KiCad board | KiCad | SVG renders in Engineering/PCB/ |
| `.kicad_prl` | 76 | — | — | none |
| `.kicad_pro` | 76 | — | — | none |
| `.plt` | 76 | — | — | none |
| `.psd` | 75 | Photoshop image | GIMP | PNG via ImageMagick |
| `.wp` | 70 | WordPerfect 5 document (original manuals) | LibreOffice Writer (rename to .wpd if it refuses) | PDF via LibreOffice |
| `.pcb` | 64 | Tango-PCB PLUS board layout (1980s DOS) | browser viewer here; KiCad after conversion (Engineering/PCB/) | interactive PCB viewer |
| `.asm` | 64 | — | — | none |
| `.o` | 60 | — | — | none |
| `.rs` | 53 | — | — | none |
| `.pic` | 37 | — | — | none |
| `.wpg` | 37 | — | — | none |
| `.gif` | 36 | image | any browser; Image Viewer | native |
| `.dsn` | 34 | OrCAD Capture schematic (binary) | OrCAD Capture (not installed) | recovered text |
| `.lst` | 33 | — | — | none |
| `.inc` | 29 | — | — | none |
| `.cdr` | 28 | CorelDRAW artwork (labels, front panels) | LibreOffice Draw; Inkscape | PDF via LibreOffice |
| `.tif` | 26 | TIFF scan | GIMP; Image Viewer | PNG via ImageMagick |
| `.bom` | 26 | — | — | none |
| `.wpd` | 24 | WordPerfect document (original manuals) | LibreOffice Writer | PDF via LibreOffice |
| `.net` | 22 | — | — | none |
| `.dbk` | 19 | — | — | none |
| `.cfg` | 16 | — | — | none |
| `.$$$` | 16 | — | — | none |
| `.toml` | 15 | — | — | none |
| `.lib` | 15 | — | — | none |
| `.inf` | 15 | — | — | none |
| `.txt` | 13 | text | any browser; Text Editor | native |
| `.err` | 13 | — | — | none |
| `.dat` | 12 | — | — | none |
| `.cod` | 12 | — | — | none |
| `.hex` | 12 | — | — | none |
| `.exe` | 11 | — | — | none |
| `.bcf` | 11 | — | — | none |
| `.zip` | 11 | — | — | none |
| `.res` | 10 | — | — | none |
| `.ins` | 10 | — | — | none |
| `.eps` | 9 | EPS artwork / logo | Inkscape; GIMP | PNG via ImageMagick |
| `.pjt` | 9 | — | — | none |
| `.xlsx` | 8 | Excel spreadsheet | LibreOffice Calc | PDF via LibreOffice |
| `.py` | 8 | — | — | none |
| `.log` | 8 | — | — | none |
| `.inx` | 8 | — | — | none |
| `.l` | 8 | — | — | none |
| `.obj` | 8 | — | — | none |
| `.bkx` | 8 | — | — | none |
| `.lock` | 7 | — | — | none |
| `.bin` | 6 | — | — | none |
| `.src` | 6 | — | — | none |
| `.blk` | 6 | — | — | none |
| `.tag` | 5 | — | — | none |
| `.clap` | 5 | — | — | none |
| `.wav` | 5 | — | — | none |
| `.rep` | 5 | — | — | none |
| `.bat` | 5 | — | — | none |
| `.pip` | 5 | — | — | none |
| `.end` | 5 | — | — | none |
| `.man` | 5 | — | — | none |
| `.smk` | 4 | — | — | none |
| `.ms` | 4 | — | — | none |
| `.hlp` | 3 | — | — | none |
| `.bot` | 3 | — | — | none |
| `.slk` | 3 | — | — | none |
| `.top` | 3 | — | — | none |
| `.drl` | 3 | — | — | none |
| `.apt` | 3 | — | — | none |
| `.sta` | 3 | — | — | none |
| `.pyc` | 3 | — | — | none |
| `.r` | 3 | — | — | none |
| `.sym` | 3 | — | — | none |
| `.ini` | 3 | — | — | none |
| `.d~n` | 3 | — | — | none |
| `.xrf` | 3 | — | — | none |
| `.doc` | 2 | Word 97 document | LibreOffice Writer | PDF via LibreOffice |
| `.epc` | 2 | — | — | none |
| `.tma` | 2 | — | — | none |
| `.mtx` | 2 | — | — | none |
| `.ova` | 2 | — | — | none |
| `.ncd` | 2 | — | — | none |
| `.drc` | 2 | — | — | none |
| `.erc` | 2 | — | — | none |
| `.was` | 2 | — | — | none |
| `.lpt` | 2 | — | — | none |
| `.mac` | 2 | — | — | none |
| `.is2` | 2 | — | — | none |
| `.dmp` | 2 | — | — | none |
| `.olb` | 2 | — | — | none |
| `.brd` | 1 | Eagle board layout | KiCad (File → Import → Eagle); browser viewer here | interactive PCB viewer |
| `.exl` | 1 | — | — | none |
| `.scr` | 1 | — | — | none |
| `.me` | 1 | — | — | none |
| `.tap` | 1 | — | — | none |
| `.cmk` | 1 | — | — | none |
| `.sld` | 1 | — | — | none |
| `.gap` | 1 | — | — | none |
| `.cmp` | 1 | — | — | none |
| `.usr` | 1 | — | — | none |
| `.js` | 1 | — | — | none |
| `.db` | 1 | — | — | none |
| `.bu` | 1 | — | — | none |
| `.now` | 1 | — | — | none |
| `.key` | 1 | — | — | none |
| `.prm` | 1 | — | — | none |
| `.dir` | 1 | — | — | none |
| `.xlt` | 1 | — | — | none |
| `.jrn` | 1 | — | — | none |
| `.ovl` | 1 | — | — | none |
| `.bug` | 1 | — | — | none |
| `.com` | 1 | — | — | none |
| `.ps` | 1 | — | — | none |
| `.dwk` | 1 | — | — | none |
| `.is1` | 1 | — | — | none |
| `.igs` | 1 | — | — | none |
| `.tmp` | 1 | — | — | none |
| `.obk` | 1 | — | — | none |
| `.out` | 1 | — | — | none |

## Not viewable yet

- **DWG** (AutoCAD R11/R12, 108 files): needs the ODA File Converter or LibreDWG to turn them into DXF, after which the DXF path above applies.
- **OrCAD .DSN / .SCH**: only text is recovered; drawings need OrCAD.
