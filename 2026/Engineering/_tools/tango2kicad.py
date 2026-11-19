"""Convert Tango-PCB Plus V2.02 ASCII boards (.PCB) to KiCad (.kicad_pcb).

Usage: python3 tango2kicad.py <board.PCB> <out folder> [--net <netlist.NET>] [--edge-layer N]

Builds the board through KiCad's own pcbnew API, so the result opens in KiCad 9.
Tango units are mils with Y up; KiCad's Y runs down, so Y is flipped about the board extents.

Tango layers:  0 top copper, 1 bottom copper, 8 top silk, 9 bottom silk, the edge layer (default 14)
becomes Edge.Cuts, every other layer N goes to KiCad User.N so nothing is lost.
Pads, lines, arcs and text that carry a component id are added to that component's footprint.
With --net, nets from a Tango netlist ([ref footprint value] / (net ref,pin ...)) are put on the pads.
"""
import json, math, os, re, shlex, sys

import pcbnew

SRC, OUT = sys.argv[1], os.path.abspath(sys.argv[2])
NET = sys.argv[sys.argv.index('--net') + 1] if '--net' in sys.argv else None
EDGE = int(sys.argv[sys.argv.index('--edge-layer') + 1]) if '--edge-layer' in sys.argv else 14
NAME = os.path.splitext(os.path.basename(SRC))[0]

recs = []
with open(SRC, errors='replace') as f:
    lines = f.read().splitlines()
i = 0
while i < len(lines):
    raw = lines[i].strip()
    i += 1
    if not raw or raw.startswith(';'):
        continue
    try:
        tok = shlex.split(raw, posix=True)
    except ValueError:  # unbalanced quote inside a text string
        tok = raw.split()
    if tok[0] == 'POLY':
        n = int(tok[2])
        pts = [tuple(int(v) for v in lines[i + k].split()[1:3]) for k in range(n)]
        i += n
        tok.append(pts)
    recs.append(tok)

board_rec = next(r for r in recs if r[0] == 'BOARD')
Y0 = int(board_rec[4])  # flip about the top of the workspace
mil = pcbnew.FromMils


def P(x, y):
    return pcbnew.VECTOR2I(mil(int(x)), mil(Y0 - int(y)))


def layer(n):
    n = int(n)
    fixed = {0: pcbnew.F_Cu, 1: pcbnew.B_Cu, 8: pcbnew.F_SilkS, 9: pcbnew.B_SilkS, EDGE: pcbnew.Edge_Cuts}
    if n in fixed:
        return fixed[n]
    return getattr(pcbnew, f'User_{n}', pcbnew.Dwgs_User) if 1 <= n <= 9 else getattr(pcbnew, f'User_{min(n - 9, 9)}', pcbnew.Dwgs_User)


board = pcbnew.BOARD()
board.SetCopperLayerCount(2)
fps, stats = {}, {'components': 0, 'pads': 0, 'tracks': 0, 'vias': 0, 'graphics': 0, 'texts': 0, 'pours': 0}
layer_use = {}

# components first, so pads and outlines can join them
for r in recs:
    if r[0] != 'COMP':
        continue
    ref, value, pattern = r[1], r[2] or r[3], r[4]
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference(ref)
    fp.SetValue(value or pattern)
    fp.SetFPID(pcbnew.LIB_ID('Tango', pattern or 'UNKNOWN'))
    fp.Reference().SetVisible(False)  # Tango keeps its own refdes text on the silk layer
    fp.Value().SetVisible(False)
    board.Add(fp)
    fp.SetPosition(P(r[6], r[7]))
    fps[r[-2]] = fp
    stats['components'] += 1


def owner(cid):
    return fps.get(cid)


free = None  # footprint for pads that belong to no component (mounting holes, test points)
for r in recs:
    kind = r[0]
    if kind == 'PAD':
        shape, w, h, hole, lay, _plate, num, x, y, cid = r[1], int(r[2]), int(r[3]), int(r[4]), r[5], r[6], r[7], r[8], r[9], r[11]
        fp = owner(cid)
        if fp is None:
            if free is None:
                free = pcbnew.FOOTPRINT(board)
                free.SetReference('H')
                free.Reference().SetVisible(False)
                free.Value().SetVisible(False)
                board.Add(free)
                free.SetPosition(P(x, y))
            fp = free
        pad = pcbnew.PAD(fp)
        pad.SetNumber(num)
        if shape == 'SQ':
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        elif shape == 'EL' and w == h or shape in ('MH', 'CR'):
            pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        else:
            pad.SetShape(pcbnew.PAD_SHAPE_OVAL)
        pad.SetSize(pcbnew.VECTOR2I(mil(w), mil(h)))
        if hole:
            pad.SetDrillSize(pcbnew.VECTOR2I(mil(hole), mil(hole)))
        if shape == 'MH':
            pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
            pad.SetLayerSet(pcbnew.PAD.UnplatedHoleMask())
        elif lay == 'AL' and hole:
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            pad.SetLayerSet(pcbnew.PAD.PTHMask())
        else:
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetLayerSet(pcbnew.PAD.SMDMask() if lay != 'BT' else pcbnew.LSET(pcbnew.B_Cu))
        fp.Add(pad)
        pad.SetPosition(P(x, y))
        stats['pads'] += 1
    elif kind == 'VIA':
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(P(r[5], r[6]))
        v.SetWidth(mil(int(r[2])))
        v.SetDrill(mil(int(r[3])))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        board.Add(v)
        stats['vias'] += 1
    elif kind == 'LINE':
        w, lay, x1, y1, x2, y2, cid = int(r[1]), int(r[2]), r[3], r[4], r[5], r[6], r[8]
        layer_use[lay] = layer_use.get(lay, 0) + 1
        if lay in (0, 1):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(P(x1, y1))
            t.SetEnd(P(x2, y2))
            t.SetWidth(mil(w))
            t.SetLayer(layer(lay))
            board.Add(t)
            stats['tracks'] += 1
        else:
            fp = owner(cid) if lay in (8, 9) else None
            s = pcbnew.PCB_SHAPE(fp or board)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(P(x1, y1))
            s.SetEnd(P(x2, y2))
            s.SetWidth(mil(max(w, 1)))
            s.SetLayer(layer(lay))
            (fp or board).Add(s)
            stats['graphics'] += 1
    elif kind == 'ARC':
        rad, start, sweep, w, lay, cx, cy, cid = int(r[1]), float(r[2]), float(r[3]), int(r[4]), int(r[5]), int(r[6]), int(r[7]), r[9]
        layer_use[lay] = layer_use.get(lay, 0) + 1
        pt = lambda a: P(cx + rad * math.cos(math.radians(a)), cy + rad * math.sin(math.radians(a)))
        fp = owner(cid) if lay in (8, 9) else None
        s = pcbnew.PCB_SHAPE(fp or board)
        if sweep >= 360:
            s.SetShape(pcbnew.SHAPE_T_CIRCLE)
            s.SetCenter(P(cx, cy))
            s.SetEnd(pt(0))
        else:
            s.SetShape(pcbnew.SHAPE_T_ARC)
            s.SetArcGeometry(pt(start), pt(start + sweep / 2), pt(start + sweep))
        s.SetWidth(mil(max(w, 1)))
        s.SetLayer(layer(lay))
        (fp or board).Add(s)
        stats['graphics'] += 1
    elif kind == 'TEXT':
        text, height, rot, width, lay, x, y = r[1], int(r[2]), int(r[3]), int(r[4]), int(r[5]), r[6], r[7]
        if text in ('.REFDES', '.TYPE'):
            continue  # placeholders; the footprint carries the real reference
        layer_use[lay] = layer_use.get(lay, 0) + 1
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text)
        t.SetLayer(layer(lay))
        t.SetTextSize(pcbnew.VECTOR2I(mil(height * 0.8), mil(height)))
        t.SetTextThickness(mil(max(width, 4)))
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
        t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_BOTTOM)
        t.SetTextAngle(pcbnew.EDA_ANGLE((rot % 4) * 90, pcbnew.DEGREES_T))
        t.SetMirrored(rot >= 4 or lay in (1, 9))
        t.SetPosition(P(x, y))
        board.Add(t)
        stats['texts'] += 1
    elif kind == 'POLY':
        lay, pts = int(r[1]), r[-1]
        layer_use[lay] = layer_use.get(lay, 0) + 1
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_POLY)
        s.SetPolyPoints([P(x, y) for x, y in pts])
        s.SetFilled(True)
        s.SetWidth(0)
        s.SetLayer(layer(lay))
        board.Add(s)
        stats['pours'] += 1

# nets from a Tango netlist
net_report = None
if NET:
    with open(NET, errors='replace') as f:
        body = f.read().replace('\r', '')
    nets = [[x.strip() for x in blk.split('\n') if x.strip()] for blk in re.findall(r'^\(\n(.*?)\n\)', body, re.M | re.S)]
    nets = [n for n in nets if n]
    pads = {(fp.GetReference(), p.GetNumber()): p for fp in board.GetFootprints() for p in fp.Pads()}
    nodes = [(n[0], tuple(node.partition(',')[::2])) for n in nets for node in n[1:]]
    hit = sum(1 for _, key in nodes if key in pads)
    applied = bool(nodes) and hit / len(nodes) >= 0.6  # an old or different revision's netlist is left off
    if applied:
        for n in nets:
            net = pcbnew.NETINFO_ITEM(board, n[0])
            board.Add(net)
            for node in n[1:]:
                pad = pads.get(tuple(node.partition(',')[::2]))
                if pad:
                    pad.SetNet(net)
    net_report = {'netlist': NET, 'nets': len(nets), 'pins_matched': hit, 'pins_in_netlist': len(nodes), 'applied': applied}

os.makedirs(OUT, exist_ok=True)
out = os.path.join(OUT, NAME + '.kicad_pcb')
pcbnew.SaveBoard(out, board)
summary = {'source': os.path.abspath(SRC), 'kicad_pcb': out, 'format': lines[0].lstrip(';').strip(),
           'edge_layer': EDGE, 'tango_layers_used': {str(k): v for k, v in sorted(layer_use.items())},
           'counts': stats, 'nets': net_report}
with open(os.path.join(OUT, NAME + '.convert.json'), 'w') as f:
    json.dump(summary, f, indent=2)
print(json.dumps(summary, indent=2))
