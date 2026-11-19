# Artwork pass: CorelDRAW panels and overlays everywhere

The user: "the corel draw and the overlays of the devices are really really good — I would take them over whatever has been shown previously."
So in every simulation, the **front and rear panels (and card-edge, rear-module, meter-bridge, overlay) artwork come from the archive's CorelDRAW (.cdr / .cmx) files**, or from Illustrator/EPS/overlay PDFs when no CDR exists. This replaces earlier PNG silk extractions and hand-drawn panels wherever a CDR exists.

ROOT = `/home/anthony/Documents/GitProjects/WBSps.ca/2026`; ARCHIVE = `/home/anthony/Downloads/WBS shuffler/WBS - DATA SHUFFLER` (read only).
Follow `tools/BUILD_BRIEF.md` (rules, privacy, no subagents, testing). You may edit ONLY the plugin files in your batch and write assets named `assets/<id>-*`.

## Per plugin
1. **Find the artwork.** Your batch lists candidate files (best guess first). Also search the archive yourself (`find "$ARCHIVE" -iname '*<code>*' \( -iname '*.cdr' -o -iname '*.cmx' -o -iname '*.ai' -o -iname '*.eps' \)`, plus `#ARTWORK #DA #2016`, `SILK`, `Silks`, `POD PANELS`, `openGear Rear Module Guides`, `Manual` folders). Prefer, in order: the final/curve (text-as-curves) version > latest date > not `Backup_of_`/`OBSOLETE`. Check the issue matches the one the plugin models; note which you chose.
2. **Convert** to SVG: `env -i HOME=$HOME PATH=/usr/bin:/bin inkscape "<in.cdr>" --export-type=svg --export-plain-svg --export-filename=/tmp/claude-1000/<dir>/x.svg` (a .png at `--export-dpi=60` is a quick look).
3. **Clean it into the panel**: keep the real geometry (outline, holes, cut-outs, connector positions, text). Drop the sheet furniture: crop marks, the side "GREEN / WHITE / FRONT / REAR" plate captions, title/date lines, other products on the same sheet. A sheet often holds separate ink plates (e.g. a GREEN plate and a WHITE plate of the same panel): register them on one panel and colour each with its real ink (POD green rgb(52,168,83), white rgb(240,240,236), others per photos) on the real panel colour (photos in `Pics/`/`Photos/`, or the plugin's current colour). Use the CURVE version so fonts are right; if only live text exists and fonts substitute badly, keep it but say so.
   Write it as `assets/<id>-front.svg` (and `-rear.svg`, `-edge.svg`, `-overlay.svg` …). Optimise: round coordinates to 2 decimals, strip metadata/unused defs; aim under ~300 KB per file.
   libcdr drops CorelDRAW hairlines (stroke width 0): give such strokes a visible width or connectors/outlines vanish. Sheets are often pinout/legend drawings, not 1:1 templates — check against Gerbers/mechanicals and report differences.
4. **Wire it in.** Replace the panel image/drawing in the plugin with the new SVG (as `<image href="siumulation-plugins/assets/…">` inside the existing panel SVG, or inlined), and **re-align every interactive control (LEDs, buttons, knobs, switches, jacks) to the holes and legends in the artwork**, using coordinates from the converted SVG. Keep every behaviour that exists now. If the old artwork is still useful (e.g. a PCB silk), keep it on a toggle labelled with its source, but the CorelDRAW art is the default.
5. **Cite the source** under the panel and in Findings with the core helper: `SIM.src('<archive-relative path>', '<short label>')`. It links the Google Drive copy of the file (Drive first, being uploaded now) and shows plain text until one exists. Use `SIM.src` for every archive file you cite in what you touch.
6. Findings: add `Artwork 2026|59: front/rear panels now from <file> (<date>)` plus anything the artwork reveals (legend vs code mismatches, issue differences, unused holes, unbuilt variants).
7. If no artwork file exists for a product (R&D notes, software-only, documents), change nothing but say so in your reply (one line). If an overlay/label/Gerber silk is the best there is, use it the same way.

## Footnotes (the user asked: "be sure to put them in the footnotes")
Every small detail the artwork or files reveal — legend typos, unexplained or undrilled holes, unbuilt variants, backslashes for slashes, files stored twice, art that disagrees with the netlist/Gerbers, renamed products — goes into a `footnotes` array in `SIM.register({...})`:
`footnotes: [{ text: 'T6403A legend says “OUT 3 Card 2” twice; position 9 should be OUT 4 Card 2.', src: '<archive-relative path of the file that shows it>' }, …]`
Plain text or light HTML (no tables), one fact per footnote, 1–2 sentences, the source file in `src`. The core numbers them at the foot of every tab (linked Drive-first) and the wiki page lists them. Keep them in Findings too.

## Test
`node --check`, then screenshot the sim tab (and any tab showing panels) per BUILD_BRIEF, and **look at it**: the artwork must be visible, correctly coloured, and controls must sit on their holes. Runtime check with a `_test_<id>.htm` copy, then delete it.

## Reply (short)
One line per plugin: artwork file used (or "none found"), assets written, anything odd.
