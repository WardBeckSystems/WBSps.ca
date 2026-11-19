#!/usr/bin/env python3
"""Cut real panel silkscreen out of a Ward-Beck "... SILK (CURVE).pdf" for the simulator.

The 2016|49 drafting sets (#ARTWORK #DA #2016) print each panel face as a separate ink
separation (e.g. POD33-M1 GREEN, POD33-M1 WHITE, POD33-M2 WHITE) between crop marks,
in black ink, with purple dashed guide lines over the top. This script:
  1. renders the PDF at 200 dpi with a transparent background (pdftocairo),
  2. keeps the black ink and drops the purple guides (re-filling ink the guides crossed),
  3. crops each separation between its crop marks,
  4. recolours it to its real ink colour and saves a transparent PNG.
Stack the PNGs for one face over the panel colour in the plugin's SVG. Image pixels
are the SVG units, so place controls on the artwork's drill crosshairs.

Usage (POD33 example, the boxes are crop-mark pixel coordinates at 200 dpi):
  python3 silk_extract.py "POD33-FRONT&REAR-SILK (CURVE).pdf" out/ \
      pod33-front-green.png:268,109,1972,421:52,168,83 \
      pod33-front-white.png:268,641,1972,952:240,240,236 \
      pod33-rear-white.png:268,1146,1972,1457:240,240,236
Run with --marks first to print the crop-mark positions it finds.
"""
import subprocess, sys, tempfile, os
import numpy as np
from PIL import Image

def render(pdf):
    d = tempfile.mkdtemp()
    subprocess.run(['pdftocairo', '-png', '-r', '200', '-transp', '-singlefile', pdf, os.path.join(d, 'p')], check=True)
    return np.array(Image.open(os.path.join(d, 'p.png')).convert('RGBA')).astype(int)

def ink_alpha(im):
    R, G, B, A = im[..., 0], im[..., 1], im[..., 2], im[..., 3]
    ink = (A > 0) & (B < 130) & (R < 120)
    guide = (A > 0) & ~ink
    fill = np.zeros_like(ink)
    for d in range(1, 5):
        for e in range(1, 5):
            fill |= guide & ((np.roll(ink, d, 1) & np.roll(ink, -e, 1)) | (np.roll(ink, d, 0) & np.roll(ink, -e, 0)))
    return np.where(fill, 255, np.where(ink, A, 0)).astype(np.uint8), ink

def marks(ink):
    H, W = ink.shape
    def runs(arr):
        best = []
        for i, line in enumerate(arr):
            r = b = 0
            for v in line:
                r = r + 1 if v else 0; b = max(b, r)
            if 60 <= b <= 120: best.append(i)
        return best
    print('vertical mark columns:', runs(ink.T))
    print('horizontal mark rows:', runs(ink))

def main():
    if len(sys.argv) < 3:
        print(__doc__); return
    im = render(sys.argv[1]); alpha, ink = ink_alpha(im)
    if sys.argv[2] == '--marks':
        marks(ink); return
    out = sys.argv[2]; os.makedirs(out, exist_ok=True)
    for spec in sys.argv[3:]:
        name, box, col = spec.split(':')
        x0, y0, x1, y1 = map(int, box.split(',')); r, g, b = map(int, col.split(','))
        a = alpha[y0:y1, x0:x1]
        img = np.zeros(a.shape + (4,), np.uint8); img[..., 0] = r; img[..., 1] = g; img[..., 2] = b; img[..., 3] = a
        Image.fromarray(img, 'RGBA').save(os.path.join(out, name), optimize=True)
        print(name, a.shape[1], 'x', a.shape[0])

if __name__ == '__main__':
    main()
