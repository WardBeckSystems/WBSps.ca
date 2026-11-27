#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""File each module's part of the earlier C++ plugin suite (2030.env/vst) into the module's own folder / repo:

    Products/Modules/<CAT>/<Mxxx>/SOFTWARE/cpp/
        README.md          what is here and where it came from
        <Mxxx>.json        the module's catalog entry (web/module_catalog.py): title, circuit summary, signal path,
                           plus its CLAP descriptor and its index in the suite
        vst/               PluginProcessor / PluginEditor / CMakeLists.txt / README.md (2030.env/vst/<dir>/)
        dsp/               the DSP cores the module's code includes (2030.env/vst/core, followed include by include)
        shell/             the CLAP shell: ClapSingleEntry.cpp (built with WBS_SINGLE_MODULE_INDEX = the index) and
                           registry.cpp: this module's descriptor, parameter table and createPluginInstance case
        gui/               layout.hpp (its ModuleGuiLayouts block), circuit.hpp (its CircuitDiagramDefinitions
                           block) and the console's panel art: module_<index>_{real,cad,signal}.svg
        notes/             the build plan (2030.env/modules/<...>_Build_Plan.md)

Not the whole build: only what this module needs, copied (the suite in 2030.env stays as it is).

    python3 tools/export_cpp_modules.py [M464 ...]
"""
import ast
import glob
import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(ROOT, '2030.env')
VST = os.path.join(ENV, 'vst')
CORE = os.path.join(VST, 'core')
REG = os.path.join(VST, 'clap_wrapper', 'ClapModuleRegistry.cpp')
SVG = os.path.join(ENV, 'web', 'static', 'svg')
PLANS = os.path.join(ENV, 'modules')

# index in the suite, module folders it belongs to, vst/ folder, descriptor, params builder, build plan(s)
MODULES = [
    (0, ['M404', 'M464'], 'M404_M464_Filter', 's_desc_m404', 'buildM404Params', ['M404_M464_Filter_Build_Plan.md']),
    (1, ['M402'], 'M402_Stepped_EQ', 's_desc_m402', 'buildM402Params', ['M402_Stepped_EQ_Build_Plan.md']),
    (2, ['M462A'], 'M462A_Channel_EQ', 's_desc_m462a', 'buildM462AParams', ['M462A_Channel_EQ_Build_Plan.md']),
    (3, ['M462B'], 'M462B_Parametric_EQ', 's_desc_m462b', 'buildM462BParams', ['M462B_Parametric_EQ_Build_Plan.md']),
    (4, ['M522B'], 'M522B_ST_Console_EQ', 's_desc_m522b', 'buildM522BParams', ['M522B_ST_Console_EQ_Build_Plan.md']),
    (5, ['M406'], 'M406_PWM_Compressor', 's_desc_m406', 'buildM406Params', ['M406_Pwm_Compressor_Build_Plan.md']),
    (10, ['M7880'], 'M7880_Intercom_Panel', 's_desc_m7880', 'buildM7880Params', ['M7880_Intercom_Panel_Build_Plan.md']),
    (11, ['M467'], 'M467_Noise_Gate', 's_desc_m467', 'buildM467Params', ['M467_Noise_Gate_Build_Plan.md']),
    (15, ['M466', 'M466M'], 'M466_Compressor_Limiter', 's_desc_m466', 'buildM466Params',
     ['M466_Compressor_Limiter_Build_Plan.md', 'M466M_Meter_Tie_Module_Build_Plan.md']),
    (20, ['M472'], None, None, None, []),
    (None, ['M405D'], 'M405D_Extended_Range_Meter', 's_desc_m405d', 'buildM405DParams', []),
]


def module_dir(code):
    hits = [d for d in glob.glob(os.path.join(ROOT, 'Products', 'Modules', '*', code)) if os.path.isdir(d)]
    return hits[0] if hits else None


def block(text, start_pat):
    """The brace-balanced block that starts at the first line matching start_pat (the line itself included)."""
    m = re.search(start_pat, text, re.M)
    if not m:
        return None
    i = text.rfind('\n', 0, m.start()) + 1
    j = text.index('{', m.start())
    depth = 0
    for k in range(j, len(text)):
        if text[k] == '{':
            depth += 1
        elif text[k] == '}':
            depth -= 1
            if depth == 0:
                end = text.find('\n', k)
                return text[i:end + 1 if end >= 0 else len(text)]
    return None


def case_block(text, func, index):
    """`case <index>: { ... }` (or `case <index>: ... break;`) inside func."""
    f = block(text, r'^[^\n]*\b' + re.escape(func) + r'\s*\(')
    if not f:
        return None
    b = block(f, r'^\s*case ' + str(index) + r':\s*\{')
    if b:
        return b
    m = re.search(r'^\s*case ' + str(index) + r':[^\n]*\n(.*?\n\s*break;\n)', f, re.S | re.M)
    return m.group(0) if m else None


def core_closure(files):
    """Every core header / source these files include, followed through core/."""
    seen, todo = [], list(files)
    while todo:
        f = todo.pop()
        try:
            text = open(f, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        for inc in re.findall(r'#include\s+"([^"]+)"', text):
            name = os.path.basename(inc)
            p = os.path.join(CORE, name)
            if os.path.exists(p) and p not in seen:
                seen.append(p)
                todo.append(p)
                cpp = p[:-4] + '.cpp' if p.endswith('.hpp') else None
                if cpp and os.path.exists(cpp) and cpp not in seen:
                    seen.append(cpp)
                    todo.append(cpp)
    return sorted(seen)


def catalog():
    src = open(os.path.join(ENV, 'web', 'module_catalog.py'), encoding='utf-8').read()
    node = next(n for n in ast.parse(src).body if isinstance(n, ast.Assign) and n.targets[0].id == 'MODULE_CATALOG')
    return {e['index']: e for e in ast.literal_eval(node.value)}


def export(index, code, vdir, desc, params, plans, cat, reg, layouts, circuits):
    mod = module_dir(code)
    if not mod:
        return f'{code}: no module folder'
    out = os.path.join(mod, 'SOFTWARE', 'cpp')
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    made = []

    def put(rel, data=None, src=None):
        p = os.path.join(out, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if src:
            shutil.copy2(src, p)
        else:
            with open(p, 'w', encoding='utf-8') as fh:
                fh.write(data)
        made.append(rel)

    vst_files = []
    if vdir and os.path.isdir(os.path.join(VST, vdir)):
        for f in sorted(os.listdir(os.path.join(VST, vdir))):
            put(f'vst/{f}', src=os.path.join(VST, vdir, f))
            vst_files.append(os.path.join(VST, vdir, f))
        for p in core_closure(vst_files):
            put(f'dsp/{os.path.basename(p)}', src=p)
    if desc:
        parts = ['// Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.',
                 f'// {code}: its part of 2030.env/vst/clap_wrapper/ClapModuleRegistry.cpp (suite index {index}).', '']
        for title, b in (('descriptor', block(reg, r'^static const clap_plugin_descriptor_t ' + desc + r'\b')),
                         ('parameters', block(reg, r'^[^\n]*\b' + params + r'\s*\(\)\s*\{')),
                         ('instance', case_block(reg, 'createPluginInstance', index) if index is not None else None)):
            if b:
                parts += [f'// --- {title} ---', b.rstrip(), '']
        put('shell/registry.cpp', '\n'.join(parts) + '\n')
        put('shell/ClapSingleEntry.cpp', src=os.path.join(VST, 'clap_wrapper', 'ClapSingleEntry.cpp'))
    if index is not None:
        lay = case_block(layouts, 'createPluginGuiModel', index)
        if code in ('M466', 'M466M'):
            extra = block(layouts, r'^inline void updateM466Layout')
            lay = (lay or '') + ('\n' + extra if extra else '')
        if lay:
            put('gui/layout.hpp', f'// {code}: its block of 2030.env/vst/core/ModuleGuiLayouts.hpp (176 x 770 = the faceplate).\n' + lay)
        cir = case_block(circuits, 'buildCircuitDiagram', index) or \
            (re.search(r'^\s*case ' + str(index) + r':[^\n]*\n.*?(?=^\s*case \d+:|\Z)', circuits, re.S | re.M) or [None])[0]
        if cir:
            put('gui/circuit.hpp', f'// {code}: its block of 2030.env/vst/core/CircuitDiagramDefinitions.hpp.\n' + cir)
        for s in sorted(glob.glob(os.path.join(SVG, f'module_{index}_*.svg'))):
            put(f'gui/{os.path.basename(s)}', src=s)
    for pl in plans:
        p = os.path.join(PLANS, pl)
        if os.path.exists(p):
            put(f'notes/{pl}', src=p)
    j = dict(cat.get(index, {})) if index is not None else {}
    d = re.search(r'static const clap_plugin_descriptor_t ' + (desc or 'x') + r'\s*=\s*\{(.*?)\};', reg, re.S)
    if d:
        strs = re.findall(r'"([^"]*)"', d.group(1))
        j['clap'] = {'id': strs[0] if strs else None, 'name': strs[1] if len(strs) > 1 else None, 'strings': strs}
    j.update({'code': code, 'suite_index': index, 'source': '2030.env/vst' + (f'/{vdir}' if vdir else '')})
    put(f'{code}.json', json.dumps(j, indent=1, ensure_ascii=False) + '\n')
    shared = ', '.join(c for c in next(m[1] for m in MODULES if code in m[1]) if c != code)
    readme = f"""# {code}: the C++ plugin (2030 suite)

{code}'s part of the earlier C++ plugin suite (`2030.env/vst` in WBSps.ca, CLAP): everything this project needs to
make the module, copied here so it lives with the module. The suite itself still builds from `2030.env/vst`
(one CMake project for all modules); this folder is the module's own code and data, not a separate build.
{f'Shared with {shared}: the suite treats them as one plugin.' if shared else ''}
The Rust VST3 / CLAP plugin is in [`../plugin`](../plugin).

| | What |
|---|---|
| [`{code}.json`]({code}.json) | the catalog entry: title, description, circuit summary, signal path (nodes, wires), CLAP id and name, suite index {index} |
| `vst/` | the module's processor (DSP chain, parameters) and editor (GUI), its CMakeLists and README |
| `dsp/` | the DSP cores it includes (filters, saturation, ballistics …) and the shared plugin frame |
| `shell/` | the CLAP shell: `ClapSingleEntry.cpp` (compiled with `WBS_SINGLE_MODULE_INDEX={index}`) and `registry.cpp`, the module's descriptor, parameter table and instance |
| `gui/` | `layout.hpp` (control positions on the 176 × 770 faceplate), `circuit.hpp` (the signal-path diagram), and the web console's panel art (`module_{index}_real/cad/signal.svg`) |
| `notes/` | the build plan |

Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""
    put('README.md', readme)
    return f'{code}: {len(made)} files → {os.path.relpath(out, ROOT)}'


def main():
    want = set(sys.argv[1:])
    reg = open(REG, encoding='utf-8').read()
    layouts = open(os.path.join(CORE, 'ModuleGuiLayouts.hpp'), encoding='utf-8').read()
    circuits = open(os.path.join(CORE, 'CircuitDiagramDefinitions.hpp'), encoding='utf-8').read()
    cat = catalog()
    for index, codes, vdir, desc, params, plans in MODULES:
        for code in codes:
            if not want or code in want:
                print(export(index, code, vdir, desc, params, plans, cat, reg, layouts, circuits))


if __name__ == '__main__':
    main()
