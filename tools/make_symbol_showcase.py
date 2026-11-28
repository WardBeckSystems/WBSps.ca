#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""PAGES/Symbols.html: the showcase of every module's synthesized drawings (tools/symbol_synth.py).

    python3 tools/make_symbol_showcase.py

A player that steps through the modules (symbol, front panel, back panel side by side), then every module as a card in
its category's colour with its files: the KiCad symbol, the PowerPoint deck, the Visio document, the DXF and the SVGs.
"""
import html, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import symbol_synth as ss

TOP = ss.TOP
OUT = os.path.join(TOP, 'PAGES', 'Symbols.html')


def main():
    rows = []
    for code, cat, repo in ss.modules():
        kd = os.path.join(repo, 'KICAD')
        if not os.path.exists(os.path.join(kd, f'{code}.pptx')):
            continue
        base = '../' + ss.rel(repo) + '/KICAD/'
        has = lambda f: os.path.exists(os.path.join(kd, f))
        rows.append({'c': code, 't': ss.title_of(repo, code), 'k': cat, 'b': base,
                     'f': has(f'{code}-front-panel.svg'), 'n': len(json.load(open(os.path.join(repo, 'RTO.json'))).get('pins', []))})
    cats = sorted({r['k'] for r in rows})
    colours = {k: ss.CATEGORY_COLOURS.get(k, ('#F4F2EC', '#444444')) for k in cats}
    shell = open(os.path.join(TOP, 'PAGES', 'Test-Procedures.html')).read()
    head = shell[:shell.index('</style>')].replace('<title>Test procedures · WBSps.ca Archive</title>',
                                                    '<title>Symbols · WBSps.ca Archive</title>')
    css = '''
.sheet { max-width:11in }
#player { display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; background:#fff; border:1px solid var(--rule); padding:10px; margin:8px 0 6px }
#player figure { margin:0; display:flex; flex-direction:column; align-items:center; gap:4px; min-width:0 }
#player img { width:100%; height:420px; object-fit:contain; background:#fff }
#player figcaption { font-size:12px; color:var(--faint) } #player .none { height:420px; display:grid; place-items:center; color:var(--faint); font-size:12px; text-align:center }
.bar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:4px 0 16px } .bar button { font:inherit; border:1px solid var(--rule); background:#fff; padding:2px 12px; cursor:pointer }
.bar .now { flex:1; font-weight:700 } .bar a { font-size:13px }
.cats { display:flex; flex-wrap:wrap; gap:6px; margin:6px 0 10px } .cats button { font:inherit; font-size:12px; border:1.5px solid; padding:1px 9px; cursor:pointer; border-radius:12px }
.cats button.off { opacity:.35 }
#q { font:inherit; width:100%; padding:4px 8px; border:1px solid var(--rule); background:#fff; margin:0 0 12px }
.grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(180px, 1fr)); gap:12px }
.card { border:1.5px solid; border-radius:4px; padding:6px; background:#fff; display:flex; flex-direction:column; gap:4px; cursor:pointer }
.card img { width:100%; height:200px; object-fit:contain; background:#fff }
.card b { font-size:15px } .card small { color:var(--faint); font-size:11px; line-height:1.3 } .card .files { font-size:11px; display:flex; flex-wrap:wrap; gap:2px 8px }
@media (max-width:700px) { #player { grid-template-columns:1fr } #player img, #player .none { height:300px } }
'''
    body = f'''</style></head><body><main class="sheet">
<div class="top"><a href="../index.html">WBSps.ca archive</a><a href="KiCad-Checks.html">KiCad checks</a><a href="../kicad.html">KiCad symbol generator</a></div>
<h1>Symbols</h1>
<p>Every module with its pinout read has its symbol <b>synthesized from its own repository's data</b> (<code>RTO.json</code>):
the KiCad symbol, and beside it the same symbol with the module's <b>front panel</b> and <b>back panel</b> as a PowerPoint deck
and a Visio document, every part an editable shape. The back panel is each connector seen from the rear, every contact with its
signal: what to wire to. Bodies are coloured by the module's kind, pins by theirs (input green, output blue, power red, ground grey,
control brown). {len(rows)} modules.</p>
<div id="player" aria-live="polite"></div>
<div class="bar"><button id="prev" title="Previous (←)">◀</button><button id="play" title="Play / pause (space)">❚❚</button>
<button id="next" title="Next (→)">▶</button><span class="now" id="now"></span><span id="files"></span></div>
<div class="cats" id="cats"></div>
<input id="q" placeholder="Find a module: M460A, compressor, intercom…">
<div class="grid" id="grid"></div>
</main>
<script>
const R = {json.dumps(rows, separators=(',', ':'))};
const C = {json.dumps(colours)};
const esc = s => String(s).replace(/[&<>"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c]);
const files = r => [['KiCad', r.c + '.kicad_sym'], ['PowerPoint', r.c + '.pptx'], ['Visio', r.c + '.vsdx'], ['DXF', r.c + '-symbol.dxf'],
  ['SVG', r.c + '-symbol.svg']].map(([n, f]) => `<a href="${{r.b}}${{encodeURIComponent(f)}}" download>${{n}}</a>`).join(' · ');
let on = new Set(Object.keys(C)), list = R, i = 0, timer = null;
function show(k) {{
  if (!list.length) return;
  i = (k + list.length) % list.length; const r = list[i], [fill, line] = C[r.k];
  const fig = (src, cap, ok = true) => ok ? `<figure><img src="${{r.b}}${{encodeURIComponent(src)}}" alt="${{esc(r.c)}} ${{cap}}"><figcaption>${{cap}}</figcaption></figure>`
    : `<figure><div class="none">No picture of the ${{esc(r.c)}} front panel<br>in the archive yet</div><figcaption>${{cap}}</figcaption></figure>`;
  document.getElementById('player').style.borderColor = line;
  document.getElementById('player').innerHTML = fig(r.c + '-symbol.svg', 'symbol') + fig(r.c + '-front-panel.svg', 'front panel', r.f) +
    fig(r.c + '-back-panel.svg', 'back panel: the connectors, rear view');
  document.getElementById('now').innerHTML = `<span style="color:${{line}}">${{esc(r.c)}}</span> ${{esc(r.t)}} <small style="color:var(--faint)">· ${{esc(r.k.toLowerCase())}} · ${{i + 1}} / ${{list.length}}</small>`;
  document.getElementById('files').innerHTML = files(r);
}}
function play(go) {{ clearInterval(timer); timer = go ? setInterval(() => show(i + 1), 4500) : null; document.getElementById('play').textContent = go ? '❚❚' : '▶︎ play'; }}
function draw() {{
  const q = document.getElementById('q').value.toLowerCase();
  list = R.filter(r => on.has(r.k) && (!q || (r.c + ' ' + r.t + ' ' + r.k).toLowerCase().includes(q)));
  document.getElementById('grid').innerHTML = list.map((r, n) => {{ const [fill, line] = C[r.k];
    return `<div class="card" data-n="${{n}}" style="border-color:${{line}};background:${{fill}}"><img loading="lazy" src="${{r.b}}${{encodeURIComponent(r.c + '-symbol.svg')}}" alt="">
      <b style="color:${{line}}">${{esc(r.c)}}</b><small>${{esc(r.t)}} · ${{r.n}} contacts${{r.f ? ' · front panel' : ''}}</small><span class="files">${{files(r)}}</span></div>`; }}).join('');
  show(0);
}}
document.getElementById('cats').innerHTML = Object.entries(C).map(([k, [f, l]]) =>
  `<button data-k="${{k}}" style="border-color:${{l}};background:${{f}};color:${{l}}">${{esc(k.toLowerCase())}}</button>`).join('');
document.getElementById('cats').onclick = e => {{ const b = e.target.closest('button'); if (!b) return;
  on.has(b.dataset.k) ? on.delete(b.dataset.k) : on.add(b.dataset.k); b.classList.toggle('off'); draw(); }};
document.getElementById('grid').onclick = e => {{ if (e.target.closest('a')) return; const c = e.target.closest('.card');
  if (c) {{ play(false); show(+c.dataset.n); scrollTo({{top: 0, behavior: 'smooth'}}); }} }};
document.getElementById('q').oninput = draw;
document.getElementById('prev').onclick = () => {{ play(false); show(i - 1); }};
document.getElementById('next').onclick = () => {{ play(false); show(i + 1); }};
document.getElementById('play').onclick = () => play(!timer);
addEventListener('keydown', e => {{ if (e.target.closest('input')) return;
  if (e.key === 'ArrowRight') {{ play(false); show(i + 1); }} if (e.key === 'ArrowLeft') {{ play(false); show(i - 1); }}
  if (e.key === ' ') {{ e.preventDefault(); play(!timer); }} }});
draw(); play(true);
</script></body></html>
'''
    open(OUT, 'w').write(head + css + body)
    print(f'{OUT}: {len(rows)} modules')


if __name__ == '__main__':
    main()
