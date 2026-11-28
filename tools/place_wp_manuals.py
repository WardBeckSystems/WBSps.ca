#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""ENGINEERING.RD-H-Drive/Word Perfect Manuals: every .WP manual rendered to PDF (LibreOffice) and put, PDF + the
original .wp, with its sub-assembly and the module / product it is used in, dated by its content (19xx: no date in
it). The originals stay in the H drive copy.   python3 tools/place_wp_manuals.py [--dry-run]
"""
import os, shutil, subprocess, sys, tempfile

TOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G = os.path.join(TOP, 'WBSps.ca', 'Github.WardBeckSystems')
SRC = os.path.join(G, 'ENGINEERING.RD-H-Drive', 'Word Perfect Manuals')
DOCS = 'DOCUMENTS/Manuals + tech DOCUMENTS/Products'
SA = lambda n: next(d for d in os.listdir(G) if d == f'SUBASSEMBLY.SA14-{n}' or d.startswith(f'SUBASSEMBLY.SA14-{n}-'))
M7880H = 'MODULES.COMMUNICATION.M7880H-Intercom-Module'
M7000 = 'MODULES.COMMUNICATION.M7000-7000-Series-Intercom'
M445 = 'MODULES.METER.M445-Extended-Range-Meter'
# file: (year (from the text: the date on the last page), code, title, homes)
W = {
 '14-152C.WP':     ('19xx', 'SA14-152C', 'PARTS LIST - MONO FILTER ASSEMBLY', [SA(152), 'MODULES.FILTERS.M522-Equalizer-Module']),
 '14-246H.WP':     ('19xx', 'SA14-246H', 'CIRCUIT DESCRIPTION - KEYSWITCH ASSEMBLY', [SA(246), M7880H]),
 '14-246HA.WP':    ('19xx', 'SA14-246HA', 'CIRCUIT DESCRIPTION - KEYSWITCH ASSEMBLY (M7880HA)', [SA(246), M7880H]),
 '14-247H.WP':     ('19xx', 'SA14-247H', 'CIRCUIT DESCRIPTION - LOGIC ASSEMBLY', [M7880H]),
 '14-271B.WP':     ('19xx', 'SA14-271B', 'CIRCUIT DESCRIPTION - AUDIO ASSEMBLY (M7882 M7883)', ['MODULES.COMMUNICATION.M7880-Intercom-System']),
 '14-273#2.WP':    ('1994', 'SA14-273', 'MANUAL - 10x1 STEREO SELECTOR ASSEMBLY', [SA(273), 'MODULES.RENAISSANCE.M905B-Studio-Monitor-Module']),
 '14-292#2.WP':    ('1995', 'SA14-292', 'MANUAL - VU METER AMPLIFIER', [SA(292)]),
 '14-292B.WP':     ('1995', 'SA14-292B', 'PARTS LIST - EXTENDED RANGE VU METER AMPLIFIER ASSEMBLY', [SA(292)]),
 '14-302.WP':      ('19xx', 'SA14-302', 'PARTS LIST - IKR-10A INTERCOM PANEL AUDIO AND KEY CONTROL', [SA(302), M7000]),
 '14-307A - 2.WP': ('1995', 'SA14-307A', 'MANUAL - EXTENDED RANGE METER LIGHT BAR', [SA(307), M445]),
 'SA14-307.WP':    ('1995', 'SA14-307', 'MANUAL - EXTENDED RANGE METER LIGHT BAR', [SA(307), M445]),
 'SA14-304.WP':    ('1995', 'SA14-304', 'CIRCUIT DESCRIPTION - LCD-ENCODER BOARD', [M445]),
 'SA14-311.WP':    ('1995', 'SA14-311', 'CIRCUIT DESCRIPTION - SPEAKER DRIVER ASSEMBLY', [SA(311), M445]),
 'SA14-311 -2 .WP':('1996', 'SA14-311', 'CIRCUIT DESCRIPTION - SPEAKER DRIVER ASSEMBLY', [SA(311), M445]),
 'SA14-312.WP':    ('1995', 'SA14-312', 'PARTS LIST - AUDIO TERMINAL ASSEMBLY BACKPLANE', [SA(312)]),
 'SA14-300.WP':    ('1995', 'SA14-300', 'CIRCUIT DESCRIPTION - CONTROL ASSEMBLY (RS8216)', [SA(300), f'{DOCS}/RS8216']),
 'SA14-301.WP':    ('1995', 'SA14-301', 'CIRCUIT DESCRIPTION - PUSHBUTTON ASSEMBLY (RS8216)', [SA(301), f'{DOCS}/RS8216']),
 'SA14-288.WP':    ('1995', 'SA14-288', 'PARTS LIST - BACKPLANE ASSEMBLY', [f'{DOCS}/SA14-288']),
 'SA14-289.WP':    ('1995', 'SA14-289', 'PARTS LIST - POWER SUPPLY ASSEMBLY', [f'{DOCS}/SA14-289']),
 'SA14-313.WP':    ('1995', 'SA14-313', 'PARTS LIST - EDAC TERMINAL BACKPLANE', [f'{DOCS}/SA14-313']),
 'IKR10.WP':       ('1995', 'IKR-10', 'MANUAL - INTERCOM CONTROL PANEL', [M7000]),
 'IKR10A.WP':      ('1995', 'IKR-10A', 'MANUAL - INTERCOM CONTROL PANEL', [M7000, SA(302)]),
 'IKR4A.WP':       ('1995', 'IKR-4A', 'MANUAL - INTERCOM CONTROL PANEL', [M7000]),
 'IPH-1E.WP':      ('19xx', 'IPH-1E', 'MANUAL - IFB BELTPACK', [M7000]),
 'IPH-4E.WP':      ('19xx', 'IPH-4E', 'MANUAL - 4-WIRE BELTPACK', [M7000]),
 'MF82-4.WP':      ('1995', 'MF82-4', 'MANUAL - QUAD DA FRAME', ['PRODUCTS.MF8200']),
 'RS8216.WP':      ('1995', 'RS8216', 'MANUAL - ROUTING SWITCHER', [f'{DOCS}/RS8216']),
 'CLK1.WP':        ('1994', 'CLK1', 'MANUAL - CLOCK', [f'{DOCS}/CLK1']),
 'TMR1.WP':        ('1994', 'TMR1', 'MANUAL - TIMER', [f'{DOCS}/TMR1']),
 'AES3-199.WP':    ('1992', 'AES3', 'SPECIFICATION - SERIAL DIGITAL AUDIO DISTRIBUTION AMPLIFIER', [f'{DOCS}/AES3']),
}


def main():
    dry = '--dry-run' in sys.argv
    missing = sorted(set(f for f in os.listdir(SRC) if f.upper().endswith('.WP')) - set(W))
    assert not missing, missing
    tmp = tempfile.mkdtemp()
    if not dry:
        subprocess.run(['soffice', f'-env:UserInstallation=file://{tmp}/lo', '--headless', '--convert-to', 'pdf',
                        '--outdir', tmp] + [os.path.join(SRC, f) for f in W], capture_output=True, check=True)
    out = []
    for f, (year, code, title, homes) in W.items():
        stem = f'{year} - {code} - {title}'
        pdf = os.path.join(tmp, os.path.splitext(f)[0] + '.pdf')
        for h in homes:
            d = os.path.join(G, h) if h.startswith('DOCUMENTS/') else os.path.join(G, h, 'MANUALS')
            out.append(os.path.join(d, stem + '.pdf'))
            out.append(os.path.join(d, stem + '.wp'))
            print(f'{f:18} -> {os.path.relpath(d, G)}/{stem}.pdf')
            if dry:
                continue
            os.makedirs(d, exist_ok=True)
            shutil.copy2(pdf, out[-2])
            shutil.copy2(os.path.join(SRC, f), out[-1])
    if not dry:
        open(os.path.join(TOP, 'tools', 'wp_manuals_placed.txt'), 'w').write('\n'.join(out) + '\n')
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
