#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""2026/Modules/svg.html: every module and its SVGs on one page.

Each module shows its front panel (MECHANICAL/<M> - front panel.svg, from _catalog/panels) and, folded under it, every
traced drawing ("<scan> (EXTRACTED).svg" beside its scan in SCHEMATICS / MECHANICAL / PINOUTS), plus the scans that
have no traced SVG yet. Re-run after new panels or traces (module_extras.py), then page_chrome.py for the site skin.

    python3 tools/make_module_svg_gallery.py
"""
import glob
import html
import json
import os
import re
from urllib.parse import quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODS = os.path.join(ROOT, '2026', 'Modules')
OUT = os.path.join(MODS, 'svg.html')
SCAN = re.compile(r'\.(jpe?g|png|tiff?|pdf)$', re.I)
DRAWING_KINDS = ('MECHANICAL', 'SCHEMATICS', 'PINOUTS')
e = html.escape


def u(path):
    return quote(path, safe='/()')


def panel_source(svg):
    try:
        with open(svg, encoding='utf-8', errors='replace') as fh:
            head = fh.read(4000)
    except OSError:
        return ''
    m = re.search(r'data-from="([^"]*)"', head)
    return html.unescape(m.group(1)) if m else ''


def module(moddir):
    cat, code = moddir.split(os.sep)[-2:]
    panel = os.path.join(moddir, 'MECHANICAL', f'{code} - front panel.svg')
    traced, untraced = [], []
    for k in DRAWING_KINDS:
        d = os.path.join(moddir, k)
        if not os.path.isdir(d):
            continue
        names = sorted(os.listdir(d))
        svgs = [n for n in names if n.endswith(' (EXTRACTED).svg')]
        for n in svgs:
            traced.append((k, n))
        for n in names:
            if not SCAN.search(n) or '(EXTRACTED)' in n or '(traced)' in n:
                continue
            stem = os.path.splitext(n)[0]
            if not any(s == f'{stem} (EXTRACTED).svg' or re.fullmatch(re.escape(stem) + r' p\d+ \(EXTRACTED\)\.svg', s)
                       for s in svgs):
                untraced.append((k, n))
    src = panel_source(panel) if os.path.exists(panel) else None
    return {'cat': cat, 'code': code, 'panel': os.path.exists(panel), 'blank': src == 'none',
            'src': src or '', 'traced': traced, 'untraced': untraced}


FRONT = re.compile(r'front ?panel|escutcheon|face ?plate|silk', re.I)


def best_drawing(traced):
    """The traced drawing that best stands in for a missing panel: a front-panel drawing, a mechanical one, then any."""
    return sorted(traced, key=lambda t: (not FRONT.search(t[1]), t[0] != 'MECHANICAL', t[1]))[0]


def card(m):
    base = f"{m['cat']}/{m['code']}"
    state = 'blank' if m['blank'] else 'panel' if m['panel'] else 'nopanel'
    if m['panel']:
        fig = (f'<a href="{u(base)}/MECHANICAL/{u(m["code"])}%20-%20front%20panel.svg"><img decoding="async" alt="{e(m["code"])} '
               f'front panel" src="{u(base)}/MECHANICAL/{u(m["code"])}%20-%20front%20panel.svg"></a>')
    elif m['traced']:
        k, n = best_drawing(m['traced'])
        href = f'{u(base)}/{k}/{u(n)}'
        fig = (f'<a href="{href}" class="stand-in" title="{e(n)}"><img loading="lazy" alt="" src="{href}">'
               f'<span>no front panel yet: {"front-panel drawing" if FRONT.search(n) else "a traced drawing"}</span></a>')
    else:
        fig = '<div class="none">no front panel SVG yet</div>'
    src = ''
    if m['src'] and m['src'] != 'none':
        src = f'<small class="src" title="{e(m["src"])}">from {e(os.path.basename(m["src"]))}</small>'
    elif m['blank']:
        src = '<small class="src">no front-panel art in the archive: outline only</small>'
    items = []
    for k, n in m['traced']:
        href = f'{u(base)}/{k}/{u(n)}'
        label = n[:-len(' (EXTRACTED).svg')]
        items.append(f'<li><a href="{href}"><img loading="lazy" alt="" src="{href}"></a><span><small>{k}</small> {e(label)}</span></li>')
    for k, n in m['untraced']:
        items.append(f'<li class="todo"><a href="../viewer.html?f=Modules/{u(base)}/{k}/{u(n)}"><div class="none">not traced yet</div>'
                     f'</a><span><small>{k}</small> {e(n)}</span></li>')
    total = len(m['traced']) + len(m['untraced'])
    drawings = ''
    if total:
        drawings = (f'<details><summary>{len(m["traced"])} of {total} drawings traced</summary>'
                    f'<ul class="dw">{"".join(items)}</ul></details>')
    else:
        drawings = '<small class="src">no drawings</small>'
    untr = ' untraced' if m['untraced'] else ''
    return (f'<section class="mod {state}{untr}" data-name="{e(m["code"].lower())} {e(m["cat"].lower())}">'
            f'<h3><a href="{u(base)}/">{e(m["code"])}</a></h3>'
            f'<figure>{fig}</figure>{src}{drawings}</section>')


def main():
    mods = [module(d.rstrip(os.sep)) for d in sorted(glob.glob(os.path.join(MODS, '*', '*', '')))]
    n_panel = sum(m['panel'] and not m['blank'] for m in mods)
    n_blank = sum(m['blank'] for m in mods)
    n_tr = sum(len(m['traced']) for m in mods)
    n_un = sum(len(m['untraced']) for m in mods)
    cats = {}
    for m in mods:
        cats.setdefault(m['cat'], []).append(m)
    body = ''.join(f'<h2 id="{e(c)}">{e(c)} <small>{len(ms)}</small></h2><div class="grid">{"".join(card(m) for m in ms)}</div>'
                   for c, ms in sorted(cats.items()))
    nav = ' '.join(f'<a href="#{e(c)}">{e(c)}</a>' for c in sorted(cats))
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Module SVGs · WBSps.ca Archive</title><link rel="icon" href="../WBS_Logo.svg">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Courier+Prime:wght@400;700&display=swap">
<style>:root{{--desk:#2b2a27;--paper:#fbfaf4;--ink:#1f1e1c;--faint:#6d6a63;--rule:#cfcabc;--link:#1f3f6b;--hl:#efe9d2}}*{{box-sizing:border-box}}
html{{background:var(--desk)}}body{{margin:0;padding:28px 16px 60px;color:var(--ink);font:15px/1.55 "Courier Prime","Courier New",Courier,monospace}}
.sheet{{position:relative;max-width:1500px;margin:0 auto;background:var(--paper);padding:clamp(16px,4vw,48px);box-shadow:0 1px 0 #d8d4c6,0 18px 40px rgba(0,0,0,.5)}}
a{{color:var(--link);text-underline-offset:3px}}.crumbs{{display:flex;flex-wrap:wrap;gap:4px 10px;margin-bottom:18px}}.crumbs a+a::before{{content:"/ ";color:var(--faint)}}
h1{{font-size:20px;margin:0 0 6px;text-transform:uppercase;text-decoration:underline;text-underline-offset:5px}}
h2{{font-size:15px;margin:28px 0 8px;text-transform:uppercase;text-decoration:underline}}small{{color:var(--faint)}}
.bar{{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;margin:10px 0 4px}}.bar input,.bar select{{font:inherit;padding:3px 6px;border:1px solid var(--rule);background:#fff}}
.nav{{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:13px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:12px}}
.mod{{border:1px solid var(--rule);background:#fbfaf4;color:#1f1e1c;padding:8px;display:flex;flex-direction:column;gap:4px;min-width:0}}
.mod h3{{margin:0;font-size:15px}}.mod a{{color:#1f3f6b!important}}.mod small,.mod summary{{color:#6d6a63}}.mod figure{{margin:0;height:300px;display:flex;align-items:center;justify-content:center;background:#f3f1ea}}
.mod figure img{{height:296px;width:auto;max-width:100%;object-fit:contain;display:block}}
.stand-in{{position:relative;display:flex;align-items:center;justify-content:center;width:100%;height:100%;text-decoration:none}}
.stand-in img{{opacity:.45}}.stand-in span{{position:absolute;left:0;right:0;bottom:0;font-size:11px;color:var(--faint);background:rgba(251,250,244,.9);padding:2px 4px;text-align:center}}.mod.blank figure{{opacity:.55}}
.none{{color:var(--faint);font-size:12px;text-align:center;padding:12px;border:1px dashed var(--rule)}}
.src{{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}}
details summary{{cursor:pointer;font-size:13px}}.dw{{list-style:none;margin:6px 0 0;padding:0;display:grid;gap:6px}}
.dw li{{display:flex;flex-direction:column;gap:2px;font-size:11px;word-break:break-word;border-top:1px dotted var(--rule);padding-top:4px}}
.dw img{{width:100%;max-height:160px;object-fit:contain;background:#f3f1ea}}.dw .none{{padding:6px}}
details[open]{{grid-column:1/-1}}.mod:has(details[open]){{grid-column:1/-1}}.mod:has(details[open]) .dw{{grid-template-columns:repeat(auto-fill,minmax(200px,1fr))}}
.hide{{display:none}}.foot{{margin-top:30px;text-align:center;color:var(--faint);font-size:13px}}</style></head><body><article class="sheet">
<div class="crumbs"><a href="../index.html">Index</a><a href="./">Modules</a><a href="svg.html">SVGs</a></div>
<h1>Module SVGs</h1>
<p><small>{len(mods)} modules · {n_panel} front panels drawn{f" · {n_blank} outline only (no panel art in the archive)" if n_blank else ""} · {n_tr} drawings traced, {n_un} not traced yet</small></p>
<div class="bar"><input id="q" type="search" placeholder="M460, FILTERS …" aria-label="Find a module">
<select id="f" aria-label="Show"><option value="">every module</option><option value="panel">with a front panel</option>
<option value="nopanel">no front panel yet</option><option value="untraced">drawings not traced yet</option></select></div>
<div class="nav">{nav}</div>
{body}
<div class="foot">An archive by Anthony Peter Kuzub · <a href="https://wbsps.kuzub.com">WBSps.Kuzub.com</a> · <a href="https://wbsps.ca">WBSps.ca</a></div>
</article><script>
(function(){{var q=document.getElementById('q'),f=document.getElementById('f'),mods=[].slice.call(document.querySelectorAll('.mod'));
function go(){{var t=q.value.trim().toLowerCase(),k=f.value;mods.forEach(function(m){{var ok=(!t||m.dataset.name.indexOf(t)>=0)&&
(!k||(k==='panel'&&m.classList.contains('panel'))||(k==='nopanel'&&!m.classList.contains('panel'))||(k==='untraced'&&m.classList.contains('untraced')));
m.classList.toggle('hide',!ok);}});}}q.addEventListener('input',go);f.addEventListener('change',go);}})();
</script></body></html>
'''
    with open(OUT, 'w', encoding='utf-8') as fh:
        fh.write(page)
    print(f'{OUT}: {len(mods)} modules, {n_panel} panels, {n_blank} outlines, {n_tr} traced, {n_un} untraced, '
          f'{os.path.getsize(OUT) // 1024} KB')


if __name__ == '__main__':
    main()
