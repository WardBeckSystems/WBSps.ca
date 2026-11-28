# WBSps.ca rule book

The golden rules for making things in the Ward-Beck Systems archive: where things live, how they are made, how they are
checked and how they are shared. Each rule comes from something that went right or wrong here. When a rule and a habit
disagree, the rule wins; when a rule is wrong, change it here.

## 1. One home for everything

1. **Every repository lives in `WBSps.ca/Github.WardBeckSystems/`**, the official local copy, never under `Products/`,
   `2026/` or `Console/`. Names repeated ten or more times are kept in a folder: `MODULES/<CAT>/`, `CONSOLE/` (and
   `CONSOLE/MODEL/`), `INTERCOM/`, `SUBASSEMBLY/`, `PRODUCTS/`. Each repo's own folder keeps its full GitHub name, and a
   family's index repo sits in its family's folder (`CONSOLE/Console`).
2. **Code never builds a clone path by hand.** Use `tools/wbs_home.py`: `repo_dir(name)` finds a repo, `nest(name)`
   says where a new one goes, `path_re()` reads one out of a path. `tools/nest_home.py` re-files the clones when a
   family reaches ten.
3. **`Products/` is being phased out.** Anything in it belongs in its repo.
4. **`2026/` is the pipeline's working tree, not the site.** It is untracked. Code that matters (the tracer,
   `2026/extractors/`) must get a repo of its own before it is lost.
5. **Public repos only as submodules.** A private one (Microcom, PRODUCTS.\*, ENGINEERING.\*, RECOVERY.\*) breaks the Pages
   build. Check visibility with `gh` before registering.
6. **`.gitignore` ignores the home folder and lets each registered family through with a `!` line.** Add the line when
   you register a new family.
7. **One fact, one place.** A module's data lives in its own repo. Copies are allowed only where the user asked for them:
   sub-assembly drawings in two places, the drawings beside the KiCad symbol.

## 2. Data first; everything else is synthesized

1. **Each repository holds its own data.** For a module that is `RTO.json` (its pinout), `Specifications.json` and
   `CircuitDescription.json`. Readings from elsewhere (RTO-144 sheets, I/O pins) are copied in, with where they came from.
2. **Outputs are always synthesized from the data, by one tool per kind of output.** Never edit an output by hand: fix
   the data and run the tool again. Symbols: `tools/symbol_synth.py`; checks: `tools/kicad_checks.py`; showcase:
   `tools/make_symbol_showcase.py`.
3. **Every output says what made it and from what** (a generator name, a `Synthesized` property, a footer line).
4. **Never invent data.** If nothing is known, there is no output, and the gap is reported. Made-up pins numbered 1 to 6
   are worse than no symbol.
5. **No placeholders, no needless content.** An empty folder or a stub README is not data. Raise anything doubled or
   needless with the user instead of making more of it.

## 3. Drawings, symbols and panels

1. **Symbols follow the KiCad library convention.** Inputs on the left, outputs on the right, power on top, grounds at the
   bottom. Each port's + and − sit together, with a blank row between groups; no-connects are hidden; everything is on
   the 2.54 mm grid.
2. **Colour carries meaning.**
   - Bodies take their module's category colour (`CATEGORY_COLOURS`).
   - Pins take their kind's colour: input green, output blue, power red, ground grey, control brown.
   - Keep the same colours everywhere.
3. **Every symbol has its family beside it, in `KICAD/`:**
   - `<M>.kicad_sym`, the KiCad symbol;
   - `<M>.pptx` and `<M>.vsdx`, a deck and a Visio document with three pages: the symbol, the front panel and the back panel;
   - `<M>-symbol.svg` and `<M>-symbol.dxf`;
   - `<M>-front-panel.svg` and `<M>-back-panel.svg`.
4. **The back panel is what to wire to.** It shows every connector from the rear, with every contact's signal.
5. **The front panel is the best source the archive has:** CorelDRAW panel art first, then a traced drawing, a layout
   drawing, then a squared-up photo. Never draw a control or a legend that is not in the source.
6. **KiCad pin names have no spaces** (KiCad shows a space as `_`). Join words with `-`, and put the polarity straight on
   the end (`MIC-IN+`). Pins without a polarity are told apart A, B.
7. **Drawing names carry the drawing number** as `[DWG ##-###-##-###]`.

## 4. Check what you make, by looking at it

1. **Render every format and look at it before calling it done.** Use the right renderer for each:
   - KiCad SVG exports in Chrome: ImageMagick also draws their hidden search text, so the names look doubled.
   - DXF with ezdxf's drawing add-on: LibreOffice's DXF import is poor.
   - PowerPoint and Visio through LibreOffice, to PDF.
2. **Validate every file a tool writes:** KiCad reads every symbol back, every deck opens, every zip tests clean.
3. **Run KiCad's own checks** (ERC on schematics, DRC on boards) with `tools/kicad_checks.py`. A schematic traced from a
   scan is lines with no parts yet, so its open wire ends are expected; say so rather than calling them faults.
4. **Count before and after.** When a move or a rewrite should change nothing, compare counts: slides per episode,
   files per repo, pins per symbol. A silent drop shows up only in the numbers.
5. **Distrust "the same picture".** A perceptual match can be wrong for screenshots of different pages with the same
   layout. Check a sample by eye before deleting.
6. **Say what was not checked.** For example: "opened in LibreOffice, not in Microsoft Visio".

## 5. Files and media

1. **The highest resolution wins, then the sharpest.** PSD becomes JPEG; pictures are at most about 1 MB and 4000 px; zips
   are unpacked. Original scans are not shrunk unless the user asks.
2. **Duplicates go to the Trash** (`gio trash`), logged in `tools/trash_log.csv`. Never `rm` archive material.
3. **Build output is not archive material.** Rust `target/`, `node_modules`, `__pycache__` and compiler leftovers stay out
   of git (`.gitignore`, and the distribution tool's junk filter).
4. **After moving files, fix every reference:** site links (`relink_media.py`), the video library paths, and the notes.
   Then search for what is still missing.

## 6. Git, with other sessions in the same tree

1. **Commit only explicit paths** (`git commit -- <paths>` or `--pathspec-from-file`). Other sessions share the index;
   a bare `git commit` takes their staged work.
2. **Record a gitlink only when its clone is pushed** (0 ahead of its upstream).
3. **A path-limited commit records the working tree.** Move an old checkout to the Trash before committing the removal of
   its gitlink.
4. **Push `main` of WBSps.ca** (Pages serves it). Never push `site/`: it is the same remote with another history.
5. **WardBeckSystems repos are pushed as WardBeckSystems.** If another login is active, pass that account's token for the
   one command; don't switch the account for everyone.
6. **Leave uncommitted work you don't understand alone,** and ask its owner or the user. (Episode 7's folder was wiped by a
   stopped render; the committed copy was the true one.)
7. **Commit messages say what and why,** and end with the co-author trailer (XTM and Tap code: none).

## 7. The website

1. **The site is built by `tools/pages_build.py`** (`.github/workflows/pages.yml`): every public submodule at its gitlink,
   small files only. Files over 1 MB, DXF drawings and build output stay in their repos, and `404.html` sends their links
   to GitHub.
2. **The Pages deploy limit is 10 GB** (a 10.70 GB site was refused). Read the size line of every build after adding repos.
3. **Site code (html, js, css) is never capped**; the home page is over 1 MB.
4. **The viewer finds its own way.** A KiCad file is drawn by KiCanvas, with its checks beside it. A file that isn't
   published is read from its repo.
5. **Audit links politely** (Pages answers too fast with 429s).
6. **Never publish claude.ai artifacts:** make local HTML or PDF files.

## 8. The video series (YOU_TUBE)

1. **Episodes name library files by path.** When the library moves, rewrite every episode's paths (`episode.py`,
   `edits.json`, including joined strings, `D + "…"` concatenations and `triple:` parts), then re-plan the whole series.
2. **The build checks every episode's pictures, not only the one you render.** A picture missing from `edits.json` is
   dropped silently, so compare slide counts.
3. **A render takes about an hour.** Plan first (`--no-video`), then render, then look at frames from it.

## 9. How to work

1. **Show, don't tell:** pictures, art and LEDs over readouts. Never show the same information twice; use short labels.
2. **Years are written `YYYY|n`** (n = YYYY − 1967), for example `1993|26`.
3. **Credit:** the archive is by Anthony Peter Kuzub. Code is © Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca).
4. **Keep private things private:** no e-mail addresses or logins in pages, commits or requests to outside services.
5. **Never `pkill -f` a pattern that is in your own command line**: it kills your own shell.
6. **Tools that misbehave in this environment:**
   - Inkscape needs a clean environment (`env -i HOME=… PATH=/usr/bin:/bin`), because the VS Code snap's libraries break it.
   - A JavaScript bundle like KiCanvas is loaded as a module (`type="module"`), so its names don't clash with the page's.
7. **Ask only for what is the user's to decide;** otherwise pick the sensible default, do it, and say so.
8. **Report faithfully:** what was done, what was checked, what was not, and what is waiting on whom.
