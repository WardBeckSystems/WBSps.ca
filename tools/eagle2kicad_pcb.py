"""Eagle XML .brd -> .kicad_pcb with KiCad 9's own importer, headless.

    python3 tools/eagle2kicad_pcb.py IN.brd OUT.kicad_pcb

KiCad has no fixed target for some Eagle layers (Pads, Vias, Origins, Test, Restrict,
Drills, Holes, Milling, Measures, and every user layer 53+). For those it calls an
interactive layer-mapping dialog; headless there is none and the importer dies with
std::bad_alloc / IO_ERROR. So first: Milling items -> Dimension (Edge.Cuts), other items
on those layers -> tDocu inside packages, Document elsewhere; then the unmappable layer
definitions are removed. Run it under a memory cap (ulimit -v) if experimenting.
"""
import os, sys, tempfile, xml.etree.ElementTree as E
import pcbnew

OK = set(range(1, 17)) | {19, 20, 21, 22, *range(25, 37), 39, 40, *range(48, 53)}

def prep(src, dst):
    t = E.parse(src); r = t.getroot(); moved = {}
    def walk(node, in_pkg):
        for ch in node:
            L = ch.get('layer')
            if L and int(L) not in OK:
                new = '20' if L == '46' else ('51' if in_pkg else '48')
                ch.set('layer', new); moved[L] = new
            walk(ch, in_pkg or ch.tag == 'package')
    walk(r, False)
    ls = r.find('drawing/layers')
    for l in list(ls):
        if int(l.get('number')) not in OK: ls.remove(l)
    t.write(dst, encoding='utf-8', xml_declaration=True)
    return moved

def main(src, out):
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        tmp = os.path.join(d, 'board.brd')
        moved = prep(src, tmp)
        b = pcbnew.PCB_IO_MGR.Load(pcbnew.PCB_IO_MGR.EAGLE, tmp)
    # SaveBoard needs a loaded project (else it asserts and aborts after writing)
    sm = pcbnew.GetSettingsManager()
    sm.LoadProject(os.path.splitext(os.path.abspath(out))[0] + '.kicad_pro')
    b.SetProject(sm.Prj())
    pcbnew.SaveBoard(out, b)
    print(f'{os.path.basename(out)}: {len(b.GetFootprints())} footprints, '
          f'{len(b.GetTracks())} tracks, {b.GetCopperLayerCount()} Cu; layers moved {moved}')

if __name__ == '__main__':
    main(*sys.argv[1:3])
