#!/usr/bin/env python3
"""ABS-1 panel artwork for the simulator (abs1.js).

The ABS-1 has no 2016 "SILK (CURVE)" PDF and no product photos in the archive.
The silkscreen source ABS1SS.CDR (CorelDRAW 5, 1998) only half-converts with libcdr:
its drill crosshairs and bars come through, its text does not. The same artwork
is printed as clean vector line art on page 1 of "ABS-1 Manual PDF.pdf" (2002),
with callout leader lines on top. This script:
  1. renders that page at 600 dpi (pdftoppm),
  2. crops the front and rear panels,
  3. removes the thin callout leaders (morphological opening; only long thin
     removed fragments are deleted, so thin text strokes stay) and their arrowheads,
  4. redraws the two panel outlines that the leaders crossed,
  5. writes black-ink and white-ink transparent PNGs:
       assets/abs1-front-black.png, abs1-front-white.png, abs1-rear-black.png, abs1-rear-white.png
Control positions in abs1.js are checked against the ABS1SS.CDR drill crosshairs.
Usage: python3 abs1_panel_extract.py "<path to ABS-1 Manual PDF.pdf>" <assets dir> <scratch dir>
"""
import sys, os, subprocess
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

pdf, outdir, tmp = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(tmp, exist_ok=True)
png = os.path.join(tmp, 'man600-1.png')
if not os.path.exists(png):
    subprocess.run(['pdftoppm', '-r', '600', '-f', '1', '-l', '1', '-png', pdf, os.path.join(tmp, 'man600')], check=True)
page = Image.open(png).convert('L')

def clean(box, arrows, segs, rects, keep, outer, inner, crop_y):
    g = np.array(page.crop(box))
    ink = g < 160
    op = ndimage.binary_opening(ink, structure=np.ones((3, 3)))
    removed = ink & ~op
    lab, n = ndimage.label(removed, structure=np.ones((3, 3)))
    kill = np.zeros_like(ink)
    for i, sl in enumerate(ndimage.find_objects(lab)):
        h = sl[0].stop - sl[0].start; w = sl[1].stop - sl[1].start
        if max(w, h) > 55: kill[sl] |= (lab[sl] == i + 1)
    kill = ndimage.binary_dilation(kill, iterations=2)
    g = g.copy(); g[kill] = 255
    im = Image.fromarray(g); d = ImageDraw.Draw(im)
    for b in arrows: d.rectangle(b, fill=255)
    im = im.crop((0, crop_y[0], im.size[0], crop_y[1]))
    d = ImageDraw.Draw(im)
    for a, b, w in segs: d.line([a, b], fill=255, width=w)
    saved = [(b, im.crop(b)) for b in keep]
    # white-out the outline band and everything outside it, then redraw both outlines
    mask = Image.new('L', im.size, 0); md = ImageDraw.Draw(mask)
    md.polygon(inner, fill=255)
    mask = Image.fromarray(ndimage.binary_erosion(np.array(mask) > 0, iterations=5).astype(np.uint8) * 255)
    base = Image.new('L', im.size, 255); base.paste(im, (0, 0), mask)
    d = ImageDraw.Draw(base)
    d.line(outer + [outer[0]], fill=0, width=4, joint='curve')
    d.line(inner + [inner[0]], fill=0, width=4, joint='curve')
    for b, c in saved: base.paste(c, b[:2])
    for b, col in rects: d.rectangle(b, fill=col)
    return base

def write(im, name):
    a = 255 - np.array(im)
    a = np.clip((a.astype(int) - 20) * 255 // 200, 0, 255).astype(np.uint8)
    for ink, suf in ((0, 'black'), (255, 'white')):
        rgba = np.zeros(a.shape + (4,), np.uint8); rgba[..., :3] = ink; rgba[..., 3] = a
        Image.fromarray(rgba, 'RGBA').save(os.path.join(outdir, f'abs1-{name}-{suf}.png'), optimize=True)

front = clean(
    (1930, 3810, 3160, 4600),
    arrows=[(66, 160, 104, 195), (66, 383, 104, 418), (675, 85, 712, 110), (898, 85, 935, 112), (1105, 145, 1138, 175),
            (1098, 390, 1130, 418), (752, 456, 785, 482), (882, 500, 915, 528), (708, 560, 740, 600), (1103, 560, 1135, 590)],
    segs=[((533, -16), (690, 84), 8), ((1010, -18), (915, 82), 8), ((26, 160), (105, 160), 26), ((1100, 145), (1199, 145), 22),
          ((1105, 384), (1230, 464), 8), ((1110, 554), (1230, 629), 8), ((765, 451), (912, 540), 8), ((900, 499), (985, 684), 8),
          ((722, 559), (722, 684), 6), ((760, 467), (780, 467), 12)],
    rects=[((657, 58, 837, 66), 0), ((906, 58, 1090, 66), 0)],
    keep=[(0, 270, 62, 350), (1165, 270, 1230, 350)],
    outer=[(40.4, 3.5), (1181, 3.5), (1222.5, 174), (1222.5, 459), (1183, 655.5), (39.5, 655.5), (3.5, 459), (3.5, 174)],
    inner=[(61.3, 22.5), (1161.4, 22.5), (1199.5, 197), (1199.5, 445), (1161.4, 635.5), (61.6, 635.5), (23.5, 445), (23.5, 197)],
    crop_y=(16, 674))
write(front, 'front')

rear = clean(
    (1890, 4990, 3220, 5800),
    arrows=[(110, 85, 150, 115), (310, 80, 345, 108), (1005, 125, 1045, 162), (195, 575, 232, 610), (665, 600, 702, 640)],
    segs=[((0, -10), (140, 105), 8), ((40, -10), (335, 100), 8), ((1025, -10), (1025, 150), 8), ((213, 590), (213, 700), 8), ((683, 610), (683, 700), 8)],
    rects=[],
    keep=[(40, 300, 100, 380), (1200, 300, 1270, 380)],
    outer=[(80.8, 31.5), (1224.2, 31.5), (1292, 340), (1224, 680.5), (80.5, 680.5), (13, 340)],
    inner=[(105, 49.5), (1205, 49.5), (1268, 340), (1205, 661.5), (105, 661.5), (39, 340)],
    crop_y=(0, 690))
write(rear, 'rear')
print('front', front.size, 'rear', rear.size)
