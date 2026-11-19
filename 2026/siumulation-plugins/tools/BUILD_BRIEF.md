# Building a product plugin for the WBS Device Simulator

ARCHIVE = `/home/anthony/Downloads/WBS shuffler/WBS - DATA SHUFFLER` (the product folders, read only).
ROOT = `/home/anthony/Documents/GitProjects/WBSps.ca/2026` (the simulator: `siumulation.html`, `siumulation-index.html`, `siumulation-plugins/`). Write plugins and assets ONLY under `ROOT/siumulation-plugins/`. Paths in this brief are relative to ROOT unless they are archive folders from `_manifest.json`, which are relative to ARCHIVE.
The archive is Ward-Beck Systems' engineering archive (broadcast audio/video products, about 1993|26 to 2017|50). Every folder has a README.md written for this archive; start there.

NOTE: the archive is being reorganised while builds run. `xxx-OBSOLETE - To Delete` has been split into family folders (`#CUSTOM #SYSTEMS`, `#AMA #SERIES`, `#AV #SERIES`, `#DEMUX #SERIES`, `#DMS #SERIES`, `#RLM #SERIES`, `#SERIALBOX #SERIES`, `#M400 #SERIES - Meter Panels`, `MISC`, …) and `XXX - ENGINEERING - 2016 RD FILES` is now `ENGINEERING - 2016 RD FILES`. Always take your folder from `_manifest.json`, and if a path is missing, search for it by name.

## Read first
- `siumulation.html`: the simulator core. It provides the transport, the tabs, and the `SIM.*` helpers: drawLanes, pulses, dotMatrix, canvas, fmtT, fmtDur, year, css, on('time'), refresh, seek.
- `siumulation-plugins/_template.js`: the plugin API and conventions.
- `siumulation-plugins/pod33.js`: the reference full plugin, and the depth and style to match. It has:
  - device state `D` plus derived functions
  - action functions that change state and log a firmware trace with real function and variable names
  - `frontSVG` and `rearSVG` built on real silkscreen PNGs, with interactive overlays
  - `lanes()` for the timeline, and an AES3 bit-level scope
  - the tabs below
- `siumulation-plugins/bigvu.js`: a smaller plugin. Its panel is drawn to scale from a mechanical drawing because the product has no silkscreen.
- `siumulation-plugins/tools/silk_extract.py`: cuts real silkscreen separations out of `… #ARTWORK #DA #2016/…SILK (CURVE).pdf`.
  1. Run it with `--marks` first to find the crop marks.
  2. Each layer is black ink under purple dashed guide lines; the script removes the guides.
  3. Recolour each layer to its real ink colour. The photos in `Pics/` or `Photos/` show the panel colour and the ink colours.
  4. Save the PNGs to `siumulation-plugins/assets/<id>-*.png`.
- If the artwork exists only as CorelDRAW `.cdr` files, convert them with Inkscape (`env -i HOME=$HOME PATH=/usr/bin:/bin inkscape in.cdr --export-type=svg`; plain `env -u SNAP…` is not enough). Inkscape only runs once the VS Code snap environment variables are cleared. libcdr loses text alignment, so re-anchor labels against the photos. The `ams81.js` plugin was built this way.
- Other plugins already in `siumulation-plugins/` (POD33, POD14A, AMS8x, openGear and others) may cover sister products. Reuse their findings and drawings, but write your own file.

## Your product's entry
Your entry in `siumulation-plugins/_manifest.json` gives the `id`, `file`, `folder` and `family`. Call `SIM.register({...})` with exactly that `id`, and with:
- `folder` and `family` exactly as in the manifest
- `product` (a short display name), `name` (`"<product> · <what it is> (YYYY|n)"`), `year`
- `summary` (2–3 sentences) and `highlights` (3–6 items)
- `depth`: `'Full model'` for code products, `'Hardware model'` for hardware or document products
- `stepUnits` and `zooms`

Use these tab ids so the index can link straight to them: `sim`, `tutorial`, `second`, `block`, `schematic`, `software`, `findings`. Leave out `software` only when the product has no logic at all.

## What every plugin must have (the user asked for all of it)
1. **One second in slow motion, as the device and its displays see it.** A zoomable timeline of the real timing: whatever the product actually has, such as samples, video lines and fields, interrupts, main-loop passes (worked out from the crystal and the code), bus and serial traffic, meter or needle ballistics, LED or display refresh, and analog signal flow through each stage.
2. **The real panel or board.** Build the front and rear panels from the real silkscreen if a SILK PDF exists anywhere for the product. Otherwise draw them to scale from mechanical, assembly or Gerber PDFs and photos, and say which file each drawing comes from. The controls must be clickable and must drive the model: knobs, buttons, switches, jacks, DashBoard parameters, PC app windows.
3. **User experience.** A full step-by-step operator TUTORIAL tab, based on the product's manual in the archive, with goals checked live and hints.
4. **How the software worked and how the buttons did things.** Each user action logs the real code path (function names, labels, registers, message bytes). A Software tab shows live diagrams: the main loop with the running step highlighted, state machines, register or protocol maps, DSP and FPGA pipelines. Hardware-only products show the signal path stage by stage instead (gains, filters, terminations, relays, pin-outs).
5. **Block diagram** (clickable) and a **schematic set**, redrawn from real pin and net names (source, .qsf/.ucf/.pin files, netlists, BOMs). Label the schematics as redrawn, not the original CAD.
6. **Findings tab.** What the product or its firmware is "up to": non-obvious behaviour, bugs, mismatches between the manual and the code, leftovers, duplicate or mislabelled files. Tie each finding to file and function names.

### Products with no code (`tier: "light"`) and R&D or document folders
These still get every tab. Simulate what the hardware or the document is about:
- analog chains: level through each stage, clipping and headroom
- distribution amplifiers (DAs): fan-out to every output, with input and output levels
- termination or rear modules: pin and connector routing, and which card they mate with
- frames: slots, power and cooling
- mechanical-only items: the assembly, with a "how it is used" tutorial
- R&D notes: model the idea under study, such as a timing analysis or a protocol, using the numbers in the documents

## Rules
- Do the work yourself. Do NOT spawn subagents, forks or workflows: the session has a hard cap of 20 concurrent agents, shared by every builder.
- Base everything on the archive's files. Mark anything not stated in the source with `<span class="tag-inf">inferred</span>` and say what it was inferred from.
- Show years as `YYYY|n`, where n = YYYY − 1967 (e.g. 2006|39). File names keep plain years.
- Use the core's CSS classes and variables (`.card`, `.grid2`, `table.kv`, `--accent`, …) so light and dark themes both work.
- No external network resources. Keep each plugin in one IIFE.
- For a keyboard handler flag, use your own prefixed global (like `window.__pod33Active`) and set it false in tabs that don't use keys.
- Never reproduce third-party logos or trade dress (Ross, Cobalt, Dolby, etc.); use plain text labels.
- PRIVACY: never include licence keys (RD15), CVs or résumés, or other personal files (RD21 `resumes/`), or anyone's personal details beyond the engineer names already in the READMEs.
- Write only these: your plugin file(s), and assets prefixed with your id in `siumulation-plugins/assets/`.
- DO NOT edit `siumulation.html`, `siumulation-index.html`, `plugins.js`, `_manifest.json`, other plugins, or any archive file outside `siumulation-plugins/`.

## Test (required)
1. Run `node --check <file>`.
2. Take a headless Chrome screenshot of every tab, with your plugin loaded on its own:
   `google-chrome --headless=new --disable-gpu --no-sandbox --allow-file-access-from-files --window-size=1400,2200 --virtual-time-budget=15000 --screenshot=/tmp/claude-1000/<yourdir>/x.png "file://$ROOT/siumulation.html?load=<file>&plugin=<id>#<tab>"`
   Look at each screenshot.
3. To catch runtime errors and drive actions, copy `siumulation.html` to `$ROOT/_test_<id>.htm` and inject a script that sets `window.onerror` to write into `document.title` and then simulates actions. Load it with `--dump-dom`, then DELETE the copy.
4. Keep scratch files under `/tmp/claude-1000/`.

## Final reply (short)
For each product: the file and asset names, the artwork you used, the main findings, the main inferred assumptions, and any test problems left.
