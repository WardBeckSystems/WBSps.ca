import re
with open('/home/anthony/Documents/GitProjects/WBSps.ca/XTM.WBSps.ca/src/views/xtm-view.ts', 'r') as f:
    content = f.read()

# Add "TONE" and numbers
ppm_block = r'''      // European Black PPM Scale: -12 to +12 dB
      const warnCol = '#facc15'; // YELLOW, NO RED!
      s += arc(this.ppmAngle(0, isSifam), this.ppmAngle(1, isSifam), R, 4, ink);
      s += arc(this.ppmAngle(18 / 24, isSifam), this.ppmAngle(1, isSifam), R + 8, 16, warnCol);

      // TONE label at top
      s += `<text x="${cx.toFixed(1)}" y="${(y0 + 80).toFixed(1)}" font-size="20" font-weight="800" text-anchor="middle" fill="${ink}">TONE</text>`;

      for (let d = -12; d <= 12; d += 2) {'''
content = content.replace('      // European Black PPM Scale: -12 to +12 dB\n      const warnCol = \'#facc15\'; // YELLOW, NO RED!\n      s += arc(this.ppmAngle(0, isSifam), this.ppmAngle(1, isSifam), R, 4, ink);\n      s += arc(this.ppmAngle(18 / 24, isSifam), this.ppmAngle(1, isSifam), R + 8, 16, warnCol);\n\n      for (let d = -12; d <= 12; d += 2) {', ppm_block)

# Add numbers below scale
# ...
with open('/home/anthony/Documents/GitProjects/WBSps.ca/XTM.WBSps.ca/src/views/xtm-view.ts', 'w') as f:
    f.write(content)
