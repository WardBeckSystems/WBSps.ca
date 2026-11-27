# WBSps.ca: everything put away

Goal (Anthony, 2026-11-27): `2026/` emptied, every file in its repository, the site at the root linking them.
No duplicate copies on disk or on the site.

## Target layout

```
WBSps.ca/                        the published site (GitHub Pages serves the root)
  index.html Home.html search.html viewer.html timeline …   site chrome, generated
  Products/
    Modules/<CATEGORY>/<Mxxx>/   submodule -> MODULES.<CAT>.<Mxxx>-<Function>
                                 its index.html = the device page (today PAGES/Mxxx.html)
    <SERIES>/<product>/          submodule -> PRODUCTS.<SERIES> (8200, METERING, MICRO, PODS, OPENGEAR …)
                                 its index.html = the product page (today PAGES/<product>.html)
    Console/                     submodule index -> CONSOLE.* and CONSOLE.MODEL.* (one repo per job)
    Intercom/                    submodule index -> INTERCOM.*, Microcom, Microcom-Simulator
  PAGES/                         wiki pages that are not one device: years, people, series, transformers, registers
  PHOTOS/ DOCUMENTS/ ADVERTISEMENTS/ Engineering/ "WEBSITE HISTORY"/
                                 submodules -> their repos; every .md sidecar beside its picture IN the repo
  tools/                         the whole pipeline (today 2026/timelines, 2026/Engineering/_tools, tools/)
  WBSps.env/  (gitignored)       pipeline state and private material: _catalog db, _sidecars, _traces,
                                 _previews, _packages, extractors, _inbox, _private
```

`2026/` and `hard drive recovery/` are gone at the end.

## Where each part of 2026/ goes

| 2026/…            | size  | goes to |
|---|---|---|
| Modules (382 submodules) | 63 G | `Products/Modules/<CAT>/<M>` (git mv; same repos) |
| Consoles          | 18 G | CONSOLE.* / INTERCOM.* repos (built 2026-11-27); local copy deleted once verify_repos.py says every file is on GitHub |
| Products          | 2.6 G | PRODUCTS.<SERIES> repos, checked out as `Products/<SERIES>` |
| PAGES             | 67 M | device pages -> each device's own folder (index.html + README.md); the rest -> root `PAGES/` |
| PHOTOS DOCUMENTS ADVERTISEMENTS Engineering "WEBSITE HISTORY" PARTS | | their repos; sidecars moved beside the pictures |
| Premo             | 1.1 G | `Premote` submodule (public) |
| siumulation-plugins, _lib | | root (site code) |
| timelines, data   | | `tools/` (scripts) + `WBSps.env/` (outputs) |
| _catalog _sidecars _traces _previews _packages extractors | 30 G | `WBSps.env/` (state; the site keeps only what pages load) |
| _inbox _private   | 13 G | `WBSps.env/` (never published) |

`hard drive recovery/` (7 G) -> RECOVERY.* repos (3 exist: WBSPS-Documents, -RAW-Photos, -Not-Uploaded);
WBS_DATA_SHUFFLER_2016, Ward-Beck Systems, Downloads_WBS_Assets, APK-WBS_Archives sorted into the module /
product / console repos where a file belongs to one, else RECOVERY.<source>. Private review first:
anything e-mail / personal stays private.

`Engineering/` -> the public `Engineering` repo (CAM, IO, KICAD, ORCAD, PCB, Plots, RTO-144, symbols), with
`Engineering/H drive` (the R&D engineering drive: D2000, D8212F, DK Technology, IKR, IPH, M7XX, PIC files,
Microcom software, RS8216, Word Perfect masters …) as a PRIVATE repo `ENGINEERING.RD-H-Drive`, a private
submodule kept out of the Pages build (private submodules break it).

`2030.env/vst` (C++ VST/CLAP: M402 … M7880, XTM meters, POD22, R6400, Master strip) -> each plugin in its own
module's repo (`<module>/SOFTWARE/vst`), the shared core / clap_wrapper / mxl / standalone in
Ward-Beck-Plugin-Core; the rest of 2030.env (engine, wbs_mxl_host, wbs_shell, web, gantt, presentations)
to its own repo.

`2030.env` is the VST plugin development tree: renamed `Ward-Beck-VST-Plugins`, its own public repo
WardBeckSystems/Ward-Beck-VST-Plugins, a submodule at the root (user, 2026-11-27). Each module's plugin
is also linked from that module's repo (SOFTWARE/README), not copied (one copy only).

Duplicates (user, 2026-11-27): when two documents are the same, the newest / best copy stays (pictures:
highest resolution, then sharpest, as audit_images.py) and the old ones go to the desktop Trash
(`gio trash`, restorable), never `rm`. Every sweep is listed in tools/trash_log.csv.

## Finding (2026-11-27): the 2026 pipeline must change first

`2026/timelines/run_all.sh` treats 2026/ as the master copy: build.py re-sorts 2026/{Modules,Products,Consoles,
ADVERTISEMENTS,DOCUMENTS,PHOTOS} from WBSps.env every run (old trees moved aside as _old_*), and make_site.py copies
the result to the root. Since the media went to the repos, the repos are the master. So before anything leaves
2026/: the page generators run with ROOT = the WBSps.ca root (writing in place, the root folders are already
make_site's copy of the same layout), the sorting stages (archive_store view / build.py --apply / make_site copy)
are retired, and 26 tools that say '2026' get one path constant (tools/paths.py). Phase 6 therefore runs as
phase 2; the module move follows it.

Added by the user, 2026-11-27 (evening):
- `ADVERTISEMENTS/` -> its own repo (WardBeckSystems/ADVERTISEMENTS), a submodule.
- `Engineering/ORCAD`: the Renaissance TV console drawings go to their modules (M920, M921, M923, M926 ->
  `<M>/SCHEMATICS/ORCAD/<set>/`), M719 to M719, POD3/4/5/7 to their PODs, SA14-321 / SA14-330 to their
  sub-assemblies.
- Sub-assemblies: every SA (SA14-xxx board assembly) its own repo `SUBASSEMBLY.SA14-xxx-<Function>`,
  collected in `Products/SubAssemblies/` (a submodule index like Console), from PARTS/SUB.ASSEMBLY,
  Engineering/PCB (`14-xxx - SA14-xxx …` boards; boards named for a module or product go to that repo) and
  Engineering/ORCAD.

## Order (each phase ends with the site working, audit_site.py clean, pushed)

1. Console + Intercom submodules -> `Products/` (git mv); `Products/Consoles` retired after
   2026/Consoles notes are scrubbed (no e-mail addresses, banned files left out).
2. Modules -> `Products/Modules`; the 18 tools that say `2026/Modules` and the viewer's `f=Modules/…`
   paths updated; links relinked (a path-move relinker: every link into or out of a moved tree).
3. Device pages generated straight into each device folder (make_wiki / page_chrome write there);
   `PAGES/Mxxx.html` becomes a redirect so old links keep working.
4. Products series -> PRODUCTS.* submodules; product pages into them.
5. PHOTOS / DOCUMENTS / ADVERTISEMENTS / Engineering: sidecars into the repos beside their pictures.
6. Pipeline: make_site.py no longer copies 2026 -> root; generators write in place; state to WBSps.env/.
7. hard drive recovery -> repos.
8. `2026/` removed; verify_repos.py: nothing left only on this disk.
