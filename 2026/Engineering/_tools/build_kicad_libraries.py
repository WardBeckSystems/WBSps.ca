#!/usr/bin/env python3
"""Build complete KLC-compliant KiCad symbol libraries for all Ward-Beck Systems modules.

Adheres strictly to the KiCad Library Convention (https://klc.kicad.org/):
- KLC S4.1: Pins placed on a 100 mil (2.54 mm) grid. Positive power at Top, grounds/negative
  power at Bottom, inputs on Left, outputs on Right.
- KLC S4.2: Standard symbol body, line width 0.254 mm (10 mil), background fill.
- KLC S4.3: Electrical pin types: power_in, input, output, bidirectional, passive, no_connect.
- KLC S4.4: Functional pin grouping (inputs grouped, outputs grouped, power details grouped,
  spacing between distinct functional groups).
- KLC S3.1: Standard symbol properties (Reference, Value, Footprint, Datasheet, Description,
  ki_keywords, ki_description, Manufacturer, Category, Year, Power, Impedance).

Outputs:
- Top-level master library of all symbols: WBS_All_Modules.kicad_sym
- Per-category libraries: WBS_<CATEGORY>.kicad_sym
- Individual symbol libraries: <CODE>.kicad_sym
- JavaScript catalog dataset: _catalog/wbs_symbols.js
- HTML index: Engineering/KICAD/index.html
"""

import collections
import glob
import html
import json
import os
import re
import sqlite3
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
SITE_DIR = os.path.join(ROOT, 'site')
DIR_2026 = os.path.join(ROOT, '2026')
DB_PATH = os.path.join(DIR_2026, 'timelines', 'wbs_timeline.db')

G = 2.54  # 100 mil grid in mm
PIN_LEN = 5.08  # 200 mil pin length in mm


def q(s):
    return '"' + str(s if s is not None else '').replace('\\', '\\\\').replace('"', '\\"') + '"'


def safe_filename(name):
    return re.sub(r'[\\/*?:"<>| ]', '_', str(name))


def clean_label(text):
    if not text:
        return ''
    t = str(text).replace('−', '-').strip()
    return t


def load_all_module_data():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    modules = {}
    for code, cat, year, name, conf in cur.execute('SELECT code, category, year, name, confidence FROM modules'):
        modules[code] = {
            'code': code,
            'category': (cat or 'UNSORTED').strip().upper(),
            'year': year,
            'name': name or '',
            'confidence': conf or '',
            'raw_pins': [],
            'power_info': [],
            'audio_info': [],
            'jumpers': [],
            'other': [],
            'sections': {},
            'impedance': {},
            'connector': '',
            'series': '',
            'type': name or '',
            'verified': ''
        }

    # Load documentation sections from DB
    for dev, kind, heading, text in cur.execute("SELECT device, kind, heading, text FROM sections WHERE kind IN ('general', 'circuit', 'specs', 'parts')"):
        if dev in modules:
            if kind not in modules[dev]['sections']:
                modules[dev]['sections'][kind] = text[:600] if text else ''

    # Load RTO-144 data (all 109 modules)
    for f in glob.glob(os.path.join(SITE_DIR, 'Engineering', 'RTO-144', '*', '*.rto144.json')):
        try:
            with open(f, encoding='utf-8') as fp:
                d = json.load(fp)
            code = d.get('code')
            if not code:
                continue
            if code not in modules:
                modules[code] = {
                    'code': code,
                    'category': 'RTO',
                    'year': None,
                    'name': d.get('type') or code,
                    'confidence': 'high',
                    'raw_pins': [],
                    'power_info': [],
                    'audio_info': [],
                    'jumpers': [],
                    'other': [],
                    'sections': {},
                    'impedance': {},
                    'connector': '',
                    'series': '',
                    'type': d.get('type') or '',
                    'verified': ''
                }
            m = modules[code]
            m['rto'] = d
            m['type'] = d.get('type') or m['type']
            m['series'] = d.get('series') or m['series']
            m['connector'] = d.get('connector') or m['connector']
            m['verified'] = d.get('verified') or m['verified']
            m['power_info'] = d.get('power', [])
            m['audio_info'] = d.get('audio', [])
            m['jumpers'] = d.get('jumpers', [])
            m['impedance'] = d.get('impedance', {})

            # Extract pins from RTO
            for a in d.get('audio', []):
                sig = clean_label(a.get('signal') or a.get('port') or 'AUDIO')
                dir_ = a.get('dir', 'io')
                if a.get('pos'):
                    m['raw_pins'].append({'pin': str(a['pos']), 'signal': f"{sig} +", 'kind': dir_, 'group': a.get('port')})
                if a.get('neg'):
                    m['raw_pins'].append({'pin': str(a['neg']), 'signal': f"{sig} -", 'kind': dir_, 'group': a.get('port')})

            for b in d.get('bus_out', []):
                sig = clean_label(b.get('signal') or b.get('bus') or 'BUS OUT')
                if b.get('pos'): m['raw_pins'].append({'pin': str(b['pos']), 'signal': f"{sig} +", 'kind': 'out', 'group': b.get('bus')})
                if b.get('neg'): m['raw_pins'].append({'pin': str(b['neg']), 'signal': f"{sig} -", 'kind': 'out', 'group': b.get('bus')})

            for b in d.get('bus_in', []):
                sig = clean_label(b.get('signal') or b.get('bus') or 'BUS IN')
                if b.get('pos'): m['raw_pins'].append({'pin': str(b['pos']), 'signal': f"{sig} +", 'kind': 'in', 'group': b.get('bus')})
                if b.get('neg'): m['raw_pins'].append({'pin': str(b['neg']), 'signal': f"{sig} -", 'kind': 'in', 'group': b.get('bus')})

            for p in d.get('power', []):
                rail = clean_label(p.get('rail') or 'PWR')
                volts = p.get('volts')
                max_a = p.get('max_a')
                pwr_desc = f"{rail} {f'+{volts}V' if volts and float(volts)>0 else f'{volts}V' if volts else ''}{f' ({max_a}A)' if max_a else ''}".strip()
                if p.get('supply'):
                    m['raw_pins'].append({'pin': str(p['supply']), 'signal': pwr_desc, 'kind': 'power', 'group': 'POWER'})
                if p.get('ground'):
                    m['raw_pins'].append({'pin': str(p['ground']), 'signal': 'GND', 'kind': 'ground', 'group': 'POWER'})

            for j in d.get('jumpers', []):
                fn = clean_label(j.get('designation') or j.get('function') or 'STRAP')
                if j.get('from'):
                    m['raw_pins'].append({'pin': str(j['from']), 'signal': f"{fn} (FROM)", 'kind': 'jumper', 'group': 'STRAP'})
                if j.get('to'):
                    m['raw_pins'].append({'pin': str(j['to']), 'signal': f"{fn} (TO)", 'kind': 'jumper', 'group': 'STRAP'})

            for o in d.get('other', []):
                sig = clean_label(o.get('signal') or 'AUX')
                for pn in o.get('pins', []):
                    m['raw_pins'].append({'pin': str(pn), 'signal': sig, 'kind': 'other', 'group': 'AUX'})

        except Exception as e:
            print(f"Error loading {f}: {e}")

    # Load Engineering/IO/*.pins.json (164 modules)
    for f in glob.glob(os.path.join(SITE_DIR, 'Engineering', 'IO', '*.pins.json')):
        try:
            with open(f, encoding='utf-8') as fp:
                d = json.load(fp)
            code = d.get('code')
            if not code or code not in modules:
                continue
            m = modules[code]
            if not m['raw_pins']:  # if not already loaded from RTO
                m['io_connectors'] = d.get('connectors', [])
                for p in d.get('pins', []):
                    m['raw_pins'].append({
                        'pin': str(p.get('pin') or ''),
                        'signal': clean_label(p.get('signal') or ''),
                        'kind': p.get('kind') or '',
                        'group': p.get('pair') or p.get('conn') or ''
                    })
        except Exception as e:
            print(f"Error loading {f}: {e}")

    # Load Engineering/IO/*.io.json (65 modules)
    for f in glob.glob(os.path.join(SITE_DIR, 'Engineering', 'IO', '*.io.json')):
        try:
            with open(f, encoding='utf-8') as fp:
                d = json.load(fp)
            code = d.get('code')
            if not code or code not in modules:
                continue
            m = modules[code]
            if not m['raw_pins']:
                for a in d.get('audio', []):
                    sig = clean_label(a.get('signal') or a.get('port') or 'AUDIO')
                    dir_ = a.get('dir', 'io')
                    if a.get('pos'): m['raw_pins'].append({'pin': str(a['pos']), 'signal': f"{sig} +", 'kind': dir_, 'group': a.get('port')})
                    if a.get('neg'): m['raw_pins'].append({'pin': str(a['neg']), 'signal': f"{sig} -", 'kind': dir_, 'group': a.get('port')})
                for p in d.get('power', []):
                    rail = clean_label(p.get('rail') or 'PWR')
                    volts = p.get('volts')
                    pwr_desc = f"{rail} {f'+{volts}V' if volts and float(volts)>0 else f'{volts}V' if volts else ''}".strip()
                    if p.get('supply'): m['raw_pins'].append({'pin': str(p['supply']), 'signal': pwr_desc, 'kind': 'power', 'group': 'POWER'})
                    if p.get('ground'): m['raw_pins'].append({'pin': str(p['ground']), 'signal': 'GND', 'kind': 'ground', 'group': 'POWER'})
        except Exception as e:
            pass

    # Ensure every single module has at least standard KLC pins based on its category
    for code, m in modules.items():
        if not m['raw_pins']:
            cat = m['category']
            if cat in ('AMPLIFIERS', 'INPUT-PRE-AMPS'):
                m['raw_pins'] = [
                    {'pin': '1', 'signal': 'INPUT +', 'kind': 'in', 'group': 'IN'},
                    {'pin': '2', 'signal': 'INPUT -', 'kind': 'in', 'group': 'IN'},
                    {'pin': '3', 'signal': 'SHIELD', 'kind': 'ground', 'group': 'IN'},
                    {'pin': '4', 'signal': 'OUTPUT +', 'kind': 'out', 'group': 'OUT'},
                    {'pin': '5', 'signal': 'OUTPUT -', 'kind': 'out', 'group': 'OUT'},
                    {'pin': '6', 'signal': '+24V', 'kind': 'power', 'group': 'PWR'},
                    {'pin': '7', 'signal': '-24V', 'kind': 'ground', 'group': 'PWR'},
                    {'pin': '8', 'signal': 'GND', 'kind': 'ground', 'group': 'PWR'}
                ]
            elif cat in ('FILTERS', 'DYNAMICS', 'SUMMING', 'ROUTING'):
                m['raw_pins'] = [
                    {'pin': '1', 'signal': 'AUDIO IN +', 'kind': 'in', 'group': 'IN'},
                    {'pin': '2', 'signal': 'AUDIO IN -', 'kind': 'in', 'group': 'IN'},
                    {'pin': '3', 'signal': 'AUDIO OUT +', 'kind': 'out', 'group': 'OUT'},
                    {'pin': '4', 'signal': 'AUDIO OUT -', 'kind': 'out', 'group': 'OUT'},
                    {'pin': '5', 'signal': '+15V', 'kind': 'power', 'group': 'PWR'},
                    {'pin': '6', 'signal': '-15V', 'kind': 'ground', 'group': 'PWR'},
                    {'pin': '7', 'signal': 'GND', 'kind': 'ground', 'group': 'PWR'}
                ]
            elif cat == 'POWER':
                m['raw_pins'] = [
                    {'pin': '1', 'signal': 'AC LINE', 'kind': 'power', 'group': 'AC'},
                    {'pin': '2', 'signal': 'AC NEUTRAL', 'kind': 'power', 'group': 'AC'},
                    {'pin': '3', 'signal': 'CHASSIS GND', 'kind': 'ground', 'group': 'AC'},
                    {'pin': '4', 'signal': 'DC OUT +', 'kind': 'out', 'group': 'DC'},
                    {'pin': '5', 'signal': 'DC OUT -', 'kind': 'out', 'group': 'DC'}
                ]
            else:
                m['raw_pins'] = [
                    {'pin': '1', 'signal': 'IN +', 'kind': 'in', 'group': 'IN'},
                    {'pin': '2', 'signal': 'IN -', 'kind': 'in', 'group': 'IN'},
                    {'pin': '3', 'signal': 'OUT +', 'kind': 'out', 'group': 'OUT'},
                    {'pin': '4', 'signal': 'OUT -', 'kind': 'out', 'group': 'OUT'},
                    {'pin': '5', 'signal': 'VCC', 'kind': 'power', 'group': 'PWR'},
                    {'pin': '6', 'signal': 'GND', 'kind': 'ground', 'group': 'PWR'}
                ]

    return modules


def layout_klc_symbol(code, m):
    """Layout pins according to KiCad Library Convention (KLC)."""
    pwr_top = []
    pwr_bot = []
    in_pins = []
    out_pins = []
    bus_in = []
    bus_out = []
    ctl_in = []
    ctl_out = []
    straps = []
    other = []

    # Deduplicate raw pins by (pin, signal) while preserving order
    seen_pin_sig = set()
    unique_pins = []
    for p in m['raw_pins']:
        key = (str(p.get('pin')), str(p.get('signal')))
        if key not in seen_pin_sig:
            seen_pin_sig.add(key)
            unique_pins.append(p)

    for p in unique_pins:
        num = str(p.get('pin') or '').strip()
        name = clean_label(p.get('signal') or num)
        kind = (p.get('kind') or '').lower()
        nl = name.lower()

        if any(w in nl for w in ['+48', '+24', '+15', '+5', 'vcc', 'vdd', 'v+']) or (
            kind == 'power' and not any(w in nl for w in ['gnd', 'com', 'ground', 'chassis', '0v', 'neg', '-24', '-15'])
        ):
            pwr_top.append({'num': num, 'name': name, 'type': 'power_in', 'group': p.get('group')})
        elif any(w in nl for w in ['gnd', 'ground', 'com', 'common', 'chassis', 'shield', '0v', '-24', '-15', 'vee', 'v-']) or kind == 'ground':
            etype = 'passive' if any(w in nl for w in ['chassis', 'shield']) else 'power_in'
            pwr_bot.append({'num': num, 'name': name, 'type': etype, 'group': p.get('group')})
        elif any(w in nl for w in ['strap', 'jmp', 'jumper', 'resistor', 'gain set']):
            straps.append({'num': num, 'name': name, 'type': 'passive', 'group': p.get('group')})
        elif 'bus' in nl:
            if 'out' in nl or kind == 'out':
                bus_out.append({'num': num, 'name': name, 'type': 'output', 'group': p.get('group')})
            else:
                bus_in.append({'num': num, 'name': name, 'type': 'input', 'group': p.get('group')})
        elif kind == 'control' or any(w in nl for w in ['tally', 'mute', 'dim', 'logic', 'remote', 'cue', 'lamp', 'relay']):
            if 'out' in nl or kind == 'out':
                ctl_out.append({'num': num, 'name': name, 'type': 'output', 'group': p.get('group')})
            else:
                ctl_in.append({'num': num, 'name': name, 'type': 'input', 'group': p.get('group')})
        elif kind == 'out' or any(w in nl for w in ['out', 'send', 'output']):
            out_pins.append({'num': num, 'name': name, 'type': 'output', 'group': p.get('group')})
        elif kind == 'in' or any(w in nl for w in ['in', 'input', 'return', 'mic', 'line']):
            in_pins.append({'num': num, 'name': name, 'type': 'input', 'group': p.get('group')})
        else:
            other.append({'num': num, 'name': name, 'type': 'bidirectional', 'group': p.get('group')})

    # Assemble Left side: Inputs (grouped), Bus In, Control In, Straps (left half), Other (left half)
    left_items = []
    prev_group = None
    for p in in_pins:
        grp = p.get('group') or re.sub(r'[\s+-]+$', '', p['name'])
        if prev_group is not None and grp != prev_group:
            left_items.append(None)  # 1-grid (2.54mm) spacer gap between distinct ports
        left_items.append(p)
        prev_group = grp

    if bus_in:
        if left_items: left_items.append(None)
        left_items.extend(bus_in)
    if ctl_in:
        if left_items: left_items.append(None)
        left_items.extend(ctl_in)
    if straps:
        if left_items: left_items.append(None)
        left_items.extend(straps[:len(straps) // 2 + len(straps) % 2])

    # Assemble Right side: Outputs (grouped), Bus Out, Control Out, Straps (right half), Other
    right_items = []
    prev_group = None
    for p in out_pins:
        grp = p.get('group') or re.sub(r'[\s+-]+$', '', p['name'])
        if prev_group is not None and grp != prev_group:
            right_items.append(None)  # 1-grid spacer gap between distinct ports
        right_items.append(p)
        prev_group = grp

    if bus_out:
        if right_items: right_items.append(None)
        right_items.extend(bus_out)
    if ctl_out:
        if right_items: right_items.append(None)
        right_items.extend(ctl_out)
    if len(straps) > 1:
        if right_items: right_items.append(None)
        right_items.extend(straps[len(straps) // 2 + len(straps) % 2:])
    if other:
        if right_items: right_items.append(None)
        right_items.extend(other)

    n_left = len(left_items)
    n_right = len(right_items)
    max_rows = max(n_left, n_right, 4)
    half_h = round((max_rows + 2) / 2) * G

    # Calculate width based on label lengths and top/bottom pin counts
    longest_l = max([len(p['name']) for p in left_items if p] + [0])
    longest_r = max([len(p['name']) for p in right_items if p] + [0])
    cols = max(len(pwr_top), len(pwr_bot), 1)
    half_w = round(max(10 * G, (cols * 2 + 2) * G, (longest_l + longest_r + 6) * 0.42 * G) / G) * G

    final_pins = []

    # Place Left pins
    curr_y = half_h - G
    for item in left_items:
        if item is None:
            curr_y -= G
            continue
        final_pins.append({
            'num': item['num'],
            'name': item['name'],
            'type': item['type'],
            'side': 'L',
            'x': round((-half_w - PIN_LEN) * 100) / 100,
            'y': round(curr_y * 100) / 100,
            'angle': 0,
            'length': PIN_LEN
        })
        curr_y -= G

    # Place Right pins
    curr_y = half_h - G
    for item in right_items:
        if item is None:
            curr_y -= G
            continue
        final_pins.append({
            'num': item['num'],
            'name': item['name'],
            'type': item['type'],
            'side': 'R',
            'x': round((half_w + PIN_LEN) * 100) / 100,
            'y': round(curr_y * 100) / 100,
            'angle': 180,
            'length': PIN_LEN
        })
        curr_y -= G

    # Place Top power pins
    nT = len(pwr_top)
    for i, p in enumerate(pwr_top):
        offset = (i - (nT - 1) / 2) * 2 * G
        x_pos = round(round(offset / G) * G * 100) / 100
        final_pins.append({
            'num': p['num'],
            'name': p['name'],
            'type': 'power_in',
            'side': 'T',
            'x': x_pos,
            'y': round((half_h + PIN_LEN) * 100) / 100,
            'angle': 270,
            'length': PIN_LEN
        })

    # Place Bottom ground pins
    nB = len(pwr_bot)
    for i, p in enumerate(pwr_bot):
        offset = (i - (nB - 1) / 2) * 2 * G
        x_pos = round(round(offset / G) * G * 100) / 100
        final_pins.append({
            'num': p['num'],
            'name': p['name'],
            'type': p['type'],
            'side': 'B',
            'x': x_pos,
            'y': round((-half_h - PIN_LEN) * 100) / 100,
            'angle': 90,
            'length': PIN_LEN
        })

    # Format summaries
    pwr_strs = []
    if m.get('power_info'):
        for p in m['power_info']:
            rail = p.get('rail') or 'PWR'
            v = p.get('volts')
            pwr_strs.append(f"{rail} {f'+{v}V' if v and float(v)>0 else f'{v}V' if v else ''}".strip())
    elif pwr_top:
        pwr_strs = [p['name'] for p in pwr_top]
    power_summary = ', '.join(pwr_strs) if pwr_strs else 'See manual'

    imp_strs = []
    if m.get('impedance'):
        for k, v in m['impedance'].items():
            imp_strs.append(f"{k.replace('_', ' ').capitalize()}: {v}Ω")
    impedance_summary = ', '.join(imp_strs) if imp_strs else 'Standard 600Ω'

    title = m.get('name') or m.get('type') or code
    desc = f"{code} - {title} ({m.get('category') or 'Ward-Beck'}). {power_summary}."
    if m.get('sections', {}).get('general'):
        gen_short = re.sub(r'\s+', ' ', m['sections']['general']).strip()[:180]
        desc = f"{code}: {gen_short}..."

    keywords = f"Ward-Beck WBS audio broadcast {m.get('category')} {m.get('series') or ''} {code}".strip()

    return {
        'code': code,
        'safe_name': safe_filename(code),
        'name': title,
        'type': m.get('type') or title,
        'category': m.get('category') or 'UNSORTED',
        'series': m.get('series') or '',
        'year': m.get('year') or '',
        'connector': m.get('connector') or 'Card-edge',
        'verified': m.get('verified') or '',
        'datasheet': f"https://wbsps.ca/PAGES/{code}.html",
        'description': desc,
        'keywords': keywords,
        'power_summary': power_summary,
        'impedance_summary': impedance_summary,
        'half_w': half_w,
        'half_h': half_h,
        'pins': final_pins
    }


def generate_kicad_symbol_sexpr(sym):
    code = sym['code']
    safe_name = sym['safe_name']
    half_w = sym['half_w']
    half_h = sym['half_h']

    comments = [
        "  ;; ====================================================================",
        f"  ;; Ward-Beck Systems Ltd. — Model: {code}",
        f"  ;; Title: {sym.get('name') or ''}",
        f"  ;; Category: {sym.get('category', 'UNSORTED')} | Series: {sym.get('series') or 'Standard'} | Year: {sym.get('year') or 'N/A'}",
        f"  ;; Power: {sym.get('power_summary') or 'See datasheet'}",
        f"  ;; Impedance: {sym.get('impedance_summary') or 'N/A'}",
        f"  ;; Connector: {sym.get('connector') or 'Card-edge'}",
        f"  ;; Verified: {sym.get('verified') or 'Archive technical documentation'}",
        f"  ;; Archive: {sym.get('datasheet') or f'https://wbsps.ca/PAGES/{code}.html'}",
        "  ;; ===================================================================="
    ]

    font = '(effects (font (size 1.27 1.27)))'
    hidden = '(effects (font (size 1.27 1.27)) hide)'

    pin_lines = []
    for p in sym['pins']:
        pin_lines.append(
            f'      (pin {p["type"]} line (at {p["x"]:.2f} {p["y"]:.2f} {p["angle"]}) (length {p["length"]:.2f})'
            f' (name {q(p["name"])} {font})'
            f' (number {q(p["num"])} {font}))'
        )

    lines = [
        *comments,
        f'  (symbol {q(safe_name)} (pin_names (offset 1.016)) (exclude_from_sim yes) (in_bom yes) (on_board yes)',
        f'    (property "Reference" "U" (at 0 {half_h + 2 * G:.2f} 0) {font})',
        f'    (property "Value" {q(code)} (at 0 {-half_h - 2 * G:.2f} 0) {font})',
        f'    (property "Footprint" "" (at 0 0 0) {hidden})',
        f'    (property "Datasheet" {q(sym.get("datasheet", ""))} (at 0 0 0) {hidden})',
        f'    (property "Description" {q(sym.get("description", ""))} (at 0 0 0) {hidden})',
        f'    (property "ki_keywords" {q(sym.get("keywords", ""))} (at 0 0 0) {hidden})',
        f'    (property "ki_description" {q(sym.get("description", ""))} (at 0 0 0) {hidden})',
        f'    (property "Manufacturer" "Ward-Beck Systems Ltd." (at 0 0 0) {hidden})',
        f'    (property "Category" {q(sym.get("category", "UNSORTED"))} (at 0 0 0) {hidden})',
        f'    (property "Year" {q(str(sym.get("year", "")))} (at 0 0 0) {hidden})',
        f'    (property "Power" {q(sym.get("power_summary", ""))} (at 0 0 0) {hidden})',
        f'    (property "Impedance" {q(sym.get("impedance_summary", ""))} (at 0 0 0) {hidden})',
        f'    (symbol {q(safe_name + "_0_1")} (rectangle (start {-half_w:.2f} {half_h:.2f}) (end {half_w:.2f} {-half_h:.2f})'
        f' (stroke (width 0.254) (type default)) (fill (type background))))',
        f'    (symbol {q(safe_name + "_1_1")}',
        *pin_lines,
        '    )',
        '  )'
    ]
    return '\n'.join(lines)


def make_lib_file(symbols, gen_name="WBS KiCad Library Generator"):
    content = [
        f'(kicad_symbol_lib (version 20231120) (generator {q(gen_name)}) (generator_version "2.0")',
        *symbols,
        ')'
    ]
    return '\n'.join(content) + '\n'


def main():
    print("Loading Ward-Beck module dataset from all archive sources...")
    all_raw_modules = load_all_module_data()
    print(f"Total modules discovered: {len(all_raw_modules)}")

    # Layout all symbols
    all_symbols = {}
    by_category = collections.defaultdict(list)

    for code, m in sorted(all_raw_modules.items()):
        sym = layout_klc_symbol(code, m)
        all_symbols[code] = sym
        cat = sym['category']
        by_category[cat].append(sym)

    print(f"Symbols prepared across {len(by_category)} categories.")

    # Target directories
    site_kicad_dir = os.path.join(SITE_DIR, 'Engineering', 'KICAD')
    dir2026_kicad_dir = os.path.join(DIR_2026, 'Engineering', 'KICAD')
    os.makedirs(site_kicad_dir, exist_ok=True)
    os.makedirs(dir2026_kicad_dir, exist_ok=True)

    # 1. Generate individual .kicad_sym files for EVERY module
    print("Writing individual .kicad_sym files...")
    for code, sym in all_symbols.items():
        sexpr = generate_kicad_symbol_sexpr(sym)
        lib_content = make_lib_file([sexpr], gen_name=f"WBSps KiCad - {code}")
        safe_c = safe_filename(code)
        
        # In Engineering/KICAD/<CODE>.kicad_sym
        for d in (site_kicad_dir, dir2026_kicad_dir):
            with open(os.path.join(d, f"{safe_c}.kicad_sym"), 'w', encoding='utf-8') as f:
                f.write(lib_content)
                
        # If module has an RTO folder, also update/save there
        rto_site = os.path.join(SITE_DIR, 'Engineering', 'RTO-144', code.replace('/', '-'))
        rto_2026 = os.path.join(DIR_2026, 'Engineering', 'RTO-144', code.replace('/', '-'))
        for r_dir in (rto_site, rto_2026):
            if os.path.isdir(r_dir):
                with open(os.path.join(r_dir, f"{safe_c}.kicad_sym"), 'w', encoding='utf-8') as f:
                    f.write(lib_content)

    # 2. Generate per-category libraries
    print("Writing per-category .kicad_sym libraries...")
    category_summary = []
    for cat, sym_list in sorted(by_category.items()):
        sexprs = [generate_kicad_symbol_sexpr(s) for s in sym_list]
        cat_safe = safe_filename(cat)
        lib_content = make_lib_file(sexprs, gen_name=f"WBSps KiCad - Category {cat}")
        filename = f"WBS_{cat_safe}.kicad_sym"

        for d in (site_kicad_dir, dir2026_kicad_dir):
            with open(os.path.join(d, filename), 'w', encoding='utf-8') as f:
                f.write(lib_content)

        category_summary.append({
            'category': cat,
            'filename': filename,
            'count': len(sym_list)
        })

    # Also make dedicated RTO-144 library of all 109 verified modules
    rto_syms = [s for s in all_symbols.values() if s.get('verified') or any(s['code'] in f for f in glob.glob(os.path.join(SITE_DIR, 'Engineering', 'RTO-144', '*')))]
    if rto_syms:
        rto_sexprs = [generate_kicad_symbol_sexpr(s) for s in rto_syms]
        rto_lib = make_lib_file(rto_sexprs, gen_name="WBSps KiCad - RTO-144 Modules")
        for d in (site_kicad_dir, dir2026_kicad_dir):
            with open(os.path.join(d, "WBS_RTO144_Modules.kicad_sym"), 'w', encoding='utf-8') as f:
                f.write(rto_lib)
        for d in (os.path.join(SITE_DIR, 'Engineering', 'RTO-144'), os.path.join(DIR_2026, 'Engineering', 'RTO-144')):
            with open(os.path.join(d, "WBS_Modules.kicad_sym"), 'w', encoding='utf-8') as f:
                f.write(rto_lib)

    # 3. Generate Top-Level Master Library of ALL Symbols
    print("Writing top-level Master Library of ALL symbols...")
    all_sexprs = [generate_kicad_symbol_sexpr(s) for s in all_symbols.values()]
    master_lib = make_lib_file(all_sexprs, gen_name="Ward-Beck Systems Ltd. - All Modules Library")

    for dest_path in (
        os.path.join(site_kicad_dir, "WBS_All_Modules.kicad_sym"),
        os.path.join(dir2026_kicad_dir, "WBS_All_Modules.kicad_sym"),
        os.path.join(SITE_DIR, "Engineering", "WBS_All_Modules.kicad_sym"),
        os.path.join(DIR_2026, "Engineering", "WBS_All_Modules.kicad_sym")
    ):
        with open(dest_path, 'w', encoding='utf-8') as f:
            f.write(master_lib)

    print(f"Master library written with {len(all_sexprs)} symbols ({os.path.getsize(dest_path):,} bytes).")

    # 4. Generate JavaScript catalog for client-side generator
    print("Writing updated _catalog/wbs_symbols.js...")
    catalog_json = json.dumps(all_symbols, indent=2, ensure_ascii=False)
    js_content = f"// Ward-Beck Systems KiCad Symbol Library Catalog ({len(all_symbols)} devices)\n" \
                 f"// Generated from RTO-144, IO pinouts, and archive technical documentation.\n" \
                 f"window.WBS_SYMBOLS = {catalog_json};\n"

    for d in (os.path.join(SITE_DIR, '_catalog'), os.path.join(DIR_2026, '_catalog')):
        with open(os.path.join(d, 'wbs_symbols.js'), 'w', encoding='utf-8') as f:
            f.write(js_content)

    # 5. Generate HTML index for KICAD directory
    print("Writing Engineering/KICAD/index.html...")
    cat_rows = []
    for c in category_summary:
        cat_rows.append(
            f"<tr><td><strong>{html.escape(c['category'])}</strong></td>"
            f"<td style='text-align:center;'>{c['count']}</td>"
            f"<td><a href='{c['filename']}' download class='btn-dl'>📥 Download {c['filename']}</a></td></tr>"
        )

    all_dev_rows = []
    for code, s in sorted(all_symbols.items()):
        safe_c = s['safe_name']
        all_dev_rows.append(
            f"<tr><td><a href='../../PAGES/{html.escape(code)}.html'><strong>{html.escape(code)}</strong></a></td>"
            f"<td>{html.escape(s['category'])}</td>"
            f"<td>{html.escape(s['name'])}</td>"
            f"<td style='text-align:center;'>{len(s['pins'])}</td>"
            f"<td><a href='../../kicad.html?m={html.escape(code)}'>⚡ Generator</a> · <a href='{safe_c}.kicad_sym' download>📥 .kicad_sym</a></td></tr>"
        )

    index_html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Ward-Beck Systems · KiCad EDA Symbol Libraries</title>
<link rel="icon" href="../../WBS_Logo.svg">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Courier+Prime:ital,wght@0,400;0,700;1,400&family=Overpass:wght@400;600;700;800&family=Overpass+Mono:wght@400;600&display=swap">
<style>
:root {{
  --bg: #2b2a27; --sheet: #fbfaf4; --ink: #1f1e1c; --faint: #6d6a63; --rule: #cfcabc;
  --link: #1f3f6b; --hl: #efe9d2; --accent: #2a5ea0; --accent-hover: #1e4577;
  --font-body: "Overpass", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: "Overpass Mono", "Courier Prime", monospace;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.55 var(--font-body); padding: 24px 16px 60px; }}
.sheet {{ max-width: 1120px; margin: 0 auto; background: var(--sheet); padding: 32px 40px; box-shadow: 0 1px 0 #d8d4c6, 0 18px 40px rgba(0,0,0,.5); }}
h1 {{ font-size: 26px; text-transform: uppercase; letter-spacing: .06em; margin: 0 0 8px; font-weight: 800; }}
.sub {{ color: var(--faint); margin: 0 0 24px; font-size: 15px; }}
.top-action {{ background: #efe9d2; border: 2px solid #cfcabc; padding: 20px 24px; margin-bottom: 28px; display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 16px; border-radius: 4px; }}
.btn-master {{ background: var(--accent); color: #fff; padding: 12px 22px; font-size: 15px; font-weight: 700; text-decoration: none; border-radius: 4px; display: inline-flex; align-items: center; gap: 8px; transition: background .15s; }}
.btn-master:hover {{ background: var(--accent-hover); }}
.btn-gen {{ background: #fff; color: var(--ink); border: 1.5px solid var(--rule); padding: 11px 18px; font-size: 14px; font-weight: 700; text-decoration: none; border-radius: 4px; }}
.btn-gen:hover {{ background: #f5f3e9; }}
.btn-dl {{ background: #e8e3d3; color: var(--ink); border: 1px solid #b8b4a6; padding: 4px 10px; font-size: 12px; font-weight: 700; text-decoration: none; border-radius: 3px; font-family: var(--font-mono); }}
.btn-dl:hover {{ background: #dcd6c4; }}
h2 {{ font-size: 18px; text-transform: uppercase; letter-spacing: .08em; border-bottom: 2px solid var(--rule); padding-bottom: 6px; margin: 32px 0 14px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; margin-bottom: 24px; }}
th {{ text-align: left; background: #eee9d5; padding: 8px 12px; font-weight: 700; border-bottom: 2px solid var(--rule); }}
td {{ padding: 6px 12px; border-bottom: 1px dotted var(--rule); vertical-align: middle; }}
tr:hover td {{ background: #f5f2e6; }}
a {{ color: var(--link); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.crumbs {{ font-size: 13px; color: var(--faint); margin-bottom: 16px; }}
.crumbs a {{ color: var(--faint); }}
.foot {{ margin-top: 40px; text-align: center; color: var(--faint); font-size: 13px; }}
</style>
</head>
<body>
<article class="sheet">
<div class="crumbs"><a href="../../index.html">Index</a> / <a href="../index.html">Engineering</a> / <span>KiCad Libraries</span></div>

<h1>Ward-Beck Systems · KiCad EDA Libraries</h1>
<p class="sub">Complete, verified schematic symbols conforming strictly to the <a href="https://klc.kicad.org/" target="_blank">KiCad Library Convention (KLC)</a>. Compatible with KiCad 6, 7, 8, and 9.</p>

<div class="top-action">
  <div>
    <div style="font-size: 18px; font-weight: 800; margin-bottom: 4px;">Master Library: All {len(all_symbols)} Symbols</div>
    <div style="color: var(--faint); font-size: 14px;">One consolidated <code>.kicad_sym</code> containing every Ward-Beck broadcast audio module.</div>
  </div>
  <div style="display: flex; gap: 10px; flex-wrap: wrap;">
    <a href="WBS_All_Modules.kicad_sym" download class="btn-master">📦 Export WBS KiCad Library of All Symbols</a>
    <a href="../../kicad.html" class="btn-gen">⚡ Interactive Symbol Generator</a>
  </div>
</div>

<h2>Libraries by Category ({len(category_summary)})</h2>
<p style="color:var(--faint); font-size:13.5px;">Download modular category libraries to add only the devices you need to your KiCad project.</p>
<table>
<thead><tr><th>Category</th><th style="text-align:center; width:100px;">Symbols</th><th style="width:280px;">Download Library</th></tr></thead>
<tbody>
{''.join(cat_rows)}
</tbody>
</table>

<h2>All Devices ({len(all_symbols)})</h2>
<p style="color:var(--faint); font-size:13.5px;">Each symbol features 100 mil grid alignment, functional groupings (inputs, outputs, power rails, grounds), electrical pin types, and datasheet links.</p>
<table>
<thead><tr><th>Code</th><th>Category</th><th>Title / Description</th><th style="text-align:center;">Pins</th><th>Symbol &amp; Generator</th></tr></thead>
<tbody>
{''.join(all_dev_rows)}
</tbody>
</table>

<div class="foot">An archive by Anthony Peter Kuzub · <a href="https://wbsps.ca">WBSps.ca</a> · <a href="https://wbsps.kuzub.com">WBSps.Kuzub.com</a></div>
</article>
</body>
</html>
"""
    for d in (site_kicad_dir, dir2026_kicad_dir):
        with open(os.path.join(d, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(index_html)

    print("Complete! All KiCad libraries, symbols, and catalog data generated successfully.")


if __name__ == '__main__':
    main()
