#!/usr/bin/env python3
# Copyright (c) 2026 Ward-Beck Systems (Ward-Beck.com - Ward-Beck.ca). All rights reserved.
"""The pages of a module's drawings (symbol, front panel, back panel) and the writers that draw any of them: SVG, a
PowerPoint deck and a Visio document. Used by tools/symbol_synth.py.

A page is a list of primitives in millimetres, y up (KiCad's sense):
    ('rect', x0, y0, x1, y1, fill, line, width, name)      fill / line: '#rrggbb' or None
    ('line', x0, y0, x1, y1, colour, width, name)
    ('circle', cx, cy, r, fill, line, width)
    ('text', x, y, text, size, colour, anchor, rot, bold)  size: the em in mm; anchor start / middle / end; rot: degrees, ccw
    ('image', png, x0, y0, x1, y1, name)                   a picture (PNG file) filling the box
"""
import base64, math, os, re, zipfile
from xml.sax.saxutils import escape as xesc

CW = 0.6                     # a monospace character's width, in ems


def text_box(t):
    """(centre x, centre y, width, height, rot) of a text primitive."""
    _, x, y, s, size, _, anchor, rot, _ = t
    w, h = len(s) * size * CW, size * 1.25
    off = {'start': w / 2, 'middle': 0, 'end': -w / 2}[anchor]
    a = math.radians(rot)
    return x + math.cos(a) * off, y + math.sin(a) * off, w, h, rot


def bbox(prims, pad=4):
    xs, ys = [], []
    for p in prims:
        if p[0] in ('rect', 'line'):
            xs += [p[1], p[3]]; ys += [p[2], p[4]]
        elif p[0] == 'circle':
            xs += [p[1] - p[3], p[1] + p[3]]; ys += [p[2] - p[3], p[2] + p[3]]
        elif p[0] == 'image':
            xs += [p[2], p[4]]; ys += [p[3], p[5]]
        elif p[0] == 'text':
            cx, cy, w, h, rot = text_box(p)
            a = math.radians(rot); dx = abs(math.cos(a)) * w / 2 + abs(math.sin(a)) * h / 2; dy = abs(math.sin(a)) * w / 2 + abs(math.cos(a)) * h / 2
            xs += [cx - dx, cx + dx]; ys += [cy - dy, cy + dy]
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


# ------------------------------------------------------------------------------------------------------------- SVG

def svg(page, title=''):
    minx, miny, maxx, maxy = bbox(page)
    k = 10
    X = lambda x: (x - minx) * k
    Y = lambda y: (maxy - y) * k
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {(maxx - minx) * k:.0f} {(maxy - miny) * k:.0f}" '
         f'font-family="Overpass Mono, Consolas, ui-monospace, monospace">', f'<title>{xesc(title)}</title>',
         '<rect width="100%" height="100%" fill="#ffffff"/>']
    for p in page:
        if p[0] == 'rect':
            _, x0, y0, x1, y1, fill, line, w, _ = p
            o.append(f'<rect x="{X(min(x0, x1)):.1f}" y="{Y(max(y0, y1)):.1f}" width="{abs(x1 - x0) * k:.1f}" height="{abs(y1 - y0) * k:.1f}" '
                     f'fill="{fill or "none"}" stroke="{line or "none"}" stroke-width="{w * k:.2f}"/>')
        elif p[0] == 'line':
            _, x0, y0, x1, y1, c, w, _ = p
            o.append(f'<line x1="{X(x0):.1f}" y1="{Y(y0):.1f}" x2="{X(x1):.1f}" y2="{Y(y1):.1f}" stroke="{c}" stroke-width="{w * k:.2f}"/>')
        elif p[0] == 'circle':
            _, cx, cy, r, fill, line, w = p
            o.append(f'<circle cx="{X(cx):.1f}" cy="{Y(cy):.1f}" r="{r * k:.1f}" fill="{fill or "none"}" stroke="{line or "none"}" stroke-width="{w * k:.2f}"/>')
        elif p[0] == 'text':
            _, x, y, s, size, c, anchor, rot, bold = p
            o.append(f'<text x="{X(x):.1f}" y="{Y(y):.1f}" font-size="{size * k:.1f}" dominant-baseline="middle" text-anchor="{anchor}" fill="{c}"'
                     + (' font-weight="700"' if bold else '') + (f' transform="rotate({-rot} {X(x):.1f} {Y(y):.1f})"' if rot else '')
                     + f'>{xesc(s)}</text>')
        elif p[0] == 'image':
            _, png, x0, y0, x1, y1, _ = p
            o.append(f'<image x="{X(x0):.1f}" y="{Y(y1):.1f}" width="{(x1 - x0) * k:.1f}" height="{(y1 - y0) * k:.1f}" '
                     f'href="data:image/png;base64,{base64.b64encode(open(png, "rb").read()).decode()}"/>')
    o.append('</svg>')
    return '\n'.join(o)


# ------------------------------------------------------------------------------------------------------- PowerPoint

def pptx(pages, path, title, footer):
    """pages: [(heading, prims)] -> one slide each, 16:9, turned upright for a tall page; every part an editable shape."""
    from pptx import Presentation
    from pptx.util import Mm, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    col = lambda h: RGBColor(int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))
    prs = Presentation()
    tall = sum(1 for _, pr in pages if (lambda b: b[3] - b[1] > b[2] - b[0])(bbox(pr)))
    SW, SH = (190.5, 338.7) if tall * 2 > len(pages) else (338.7, 190.5)
    prs.slide_width, prs.slide_height = Mm(SW), Mm(SH)
    for heading, prims in pages:
        minx, miny, maxx, maxy = bbox(prims)
        s = min((SW - 16) / (maxx - minx), (SH - 30) / (maxy - miny))
        ox, oy = (SW - (maxx - minx) * s) / 2, 14 + (SH - 30 - (maxy - miny) * s) / 2
        X = lambda x: Mm(ox + (x - minx) * s)
        Y = lambda y: Mm(oy + (maxy - y) * s)
        slide = prs.slides.add_slide(prs.slide_layouts[6])

        def tbox(t, cx, cy, w, h, size, colour, align, rot=0, bold=False):
            if not str(t).strip():
                return None
            b = slide.shapes.add_textbox(Mm(cx - w / 2), Mm(cy - h / 2), Mm(w), Mm(h))
            tf = b.text_frame; tf.word_wrap = False; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
            para = tf.paragraphs[0]; para.text = t; para.alignment = align
            r = para.runs[0]; r.font.size, r.font.bold, r.font.name = Pt(size), bold, 'Consolas'; r.font.color.rgb = col(colour)
            b.rotation = (-rot) % 360
            return b
        tbox(heading, SW / 2, 8, SW - 16, 10, 18, '#1F1E1C', PP_ALIGN.CENTER, bold=True)
        tbox(footer, SW / 2, SH - 6, SW - 16, 6, 9, '#6D6A63', PP_ALIGN.CENTER)
        for p in prims:
            if p[0] == 'rect':
                _, x0, y0, x1, y1, fill, line, w, name = p
                r = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, X(min(x0, x1)), Y(max(y0, y1)), Mm(abs(x1 - x0) * s), Mm(abs(y1 - y0) * s))
                if fill: r.fill.solid(); r.fill.fore_color.rgb = col(fill)
                else: r.fill.background()
                if line: r.line.color.rgb, r.line.width = col(line), Pt(max(.5, w * s * 2.835))
                else: r.line.fill.background()
                r.shadow.inherit = False
                if name: r.name = name
            elif p[0] == 'line':
                _, x0, y0, x1, y1, c, w, name = p
                ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, X(x0), Y(y0), X(x1), Y(y1))
                ln.line.color.rgb, ln.line.width = col(c), Pt(max(.75, w * s * 2.835))
                if name: ln.name = name
            elif p[0] == 'circle':
                _, cx, cy, rr, fill, line, w = p
                o = slide.shapes.add_shape(MSO_SHAPE.OVAL, X(cx - rr), Y(cy + rr), Mm(2 * rr * s), Mm(2 * rr * s))
                if fill: o.fill.solid(); o.fill.fore_color.rgb = col(fill)
                if line: o.line.color.rgb, o.line.width = col(line), Pt(max(.5, w * s * 2.835))
                o.shadow.inherit = False
            elif p[0] == 'text':
                cx, cy, w, h, rot = text_box(p)
                align = {'start': PP_ALIGN.LEFT, 'middle': PP_ALIGN.CENTER, 'end': PP_ALIGN.RIGHT}[p[6]]
                tbox(p[3], ox + (cx - minx) * s, oy + (maxy - cy) * s, w * s * 1.08, h * s, max(5, p[4] * s * 2.835), p[5], align, rot, p[8])
            elif p[0] == 'image':
                _, png, x0, y0, x1, y1, name = p
                pic = slide.shapes.add_picture(png, X(x0), Y(y1), Mm((x1 - x0) * s), Mm((y1 - y0) * s))
                if name: pic.name = name
    prs.core_properties.title, prs.core_properties.author = title, 'Ward-Beck Systems'
    prs.save(path)


# ------------------------------------------------------------------------------------------------------------ Visio

NS = 'xmlns="http://schemas.microsoft.com/office/visio/2012/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
RELS = 'http://schemas.openxmlformats.org/package/2006/relationships'
HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def _cells(**c):
    return ''.join(f'<Cell N="{k}" V="{v}"/>' for k, v in c.items())


def vsdx(pages, path, title):
    """pages: [(heading, prims)] -> a Visio document with one page each (written by hand: the parts Visio and LibreOffice read)."""
    IN = 25.4
    files, page_list, page_rels, media, ctypes = {}, [], [], [], set()
    for n, (heading, prims) in enumerate(pages, 1):
        minx, miny, maxx, maxy = bbox(prims)
        pw, ph = (maxx - minx) / IN, (maxy - miny) / IN + 0.5
        X = lambda x: (x - minx) / IN
        Y = lambda y: (y - miny) / IN
        shapes, rels, sid = [], [], [0]

        def shape(cx, cy, w, h, geom=None, text='', fill=None, line=None, weight=0.01, size=0.1, colour='#1F1E1C', align=1,
                  angle=0.0, bold=False, name='', foreign=None):
            sid[0] += 1
            w, h = max(w, 0.0001), max(h, 0.0001)
            c = _cells(PinX=f'{cx:.4f}', PinY=f'{cy:.4f}', Width=f'{w:.4f}', Height=f'{h:.4f}', LocPinX=f'{w / 2:.4f}', LocPinY=f'{h / 2:.4f}',
                       Angle=f'{angle:.6f}', LeftMargin=0, RightMargin=0, TopMargin=0, BottomMargin=0, VerticalAlign=1)
            c += _cells(LineColor=line, LineWeight=f'{weight:.4f}', LinePattern=1) if line else _cells(LinePattern=0)
            c += _cells(FillForegnd=fill, FillPattern=1) if fill else _cells(FillPattern=0)
            g = ''
            if geom:
                rows = ''.join(f'<Row T="{t}" IX="{i + 1}"><Cell N="X" V="{gx:.4f}"/><Cell N="Y" V="{gy:.4f}"/></Row>' for i, (t, gx, gy) in enumerate(geom))
                g = f'<Section N="Geometry" IX="0">{_cells(NoFill=0 if fill else 1, NoLine=0 if line else 1)}{rows}</Section>'
            t = ''
            if text:
                t = (f'<Section N="Character"><Row IX="0"><Cell N="Size" V="{size:.4f}" U="IN"/><Cell N="Color" V="{colour}"/>'
                     f'<Cell N="Style" V="{1 if bold else 0}"/></Row></Section><Section N="Paragraph"><Row IX="0"><Cell N="HorzAlign" V="{align}"/>'
                     f'</Row></Section><Text>{xesc(text)}</Text>')
            if foreign:   # a picture: where it sits in the shape, then the picture itself
                c += _cells(ImgOffsetX=0, ImgOffsetY=0, ImgWidth=f'{w:.4f}', ImgHeight=f'{h:.4f}')
            fd = f'<ForeignData ForeignType="Bitmap" CompressionType="PNG"><Rel r:id="{foreign}"/></ForeignData>' if foreign else ''
            kind = 'Foreign' if foreign else 'Shape'
            shapes.append(f'<Shape ID="{sid[0]}" NameU="{xesc(name or kind + str(sid[0]))}" Type="{kind}" LineStyle="0" FillStyle="0" TextStyle="0">'
                          f'{c}{g}{t}{fd}</Shape>')
        shape(pw / 2, ph - 0.25, pw, 0.3, text=heading, size=0.16, bold=True)
        for p in prims:
            if p[0] == 'rect':
                _, x0, y0, x1, y1, fill, line, w, name = p
                ww, hh = abs(X(x1) - X(x0)), abs(Y(y1) - Y(y0))
                shape((X(x0) + X(x1)) / 2, (Y(y0) + Y(y1)) / 2, ww, hh, [('MoveTo', 0, 0), ('LineTo', ww, 0), ('LineTo', ww, hh), ('LineTo', 0, hh), ('LineTo', 0, 0)],
                      fill=fill, line=line, weight=w / IN, name=name)
            elif p[0] == 'line':
                _, x0, y0, x1, y1, c, w, name = p
                lx, ly = min(X(x0), X(x1)), min(Y(y0), Y(y1))
                ww, hh = abs(X(x1) - X(x0)) or 0.0001, abs(Y(y1) - Y(y0)) or 0.0001
                shape(lx + ww / 2, ly + hh / 2, ww, hh, [('MoveTo', X(x0) - lx, Y(y0) - ly), ('LineTo', X(x1) - lx, Y(y1) - ly)], line=c, weight=w / IN, name=name)
            elif p[0] == 'circle':
                _, cx, cy, r, fill, line, w = p
                d = 2 * r / IN
                shape(X(cx), Y(cy), d, d, fill=fill, line=line, weight=w / IN)   # its geometry, an Ellipse row, added here:
                shapes[-1] = shapes[-1].replace('</Shape>', f'<Section N="Geometry" IX="0">{_cells(NoFill=0 if fill else 1, NoLine=0)}'
                                                f'<Row T="Ellipse" IX="1">{_cells(X=d / 2, Y=d / 2, A=d, B=d / 2, C=d / 2, D=d)}</Row></Section></Shape>')
            elif p[0] == 'text' and str(p[3]).strip():
                cx, cy, w, h, rot = text_box(p)
                shape(X(cx), Y(cy), w / IN * 1.08, h / IN, text=p[3], size=p[4] / IN, colour=p[5],
                      align={'start': 0, 'middle': 1, 'end': 2}[p[6]], angle=math.radians(rot), bold=p[8])
            elif p[0] == 'image':
                _, png, x0, y0, x1, y1, name = p
                media.append(png); rid = f'rId{len(rels) + 1}'
                rels.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                            f'Target="../media/image{len(media)}.png"/>')
                shape((X(x0) + X(x1)) / 2, (Y(y0) + Y(y1)) / 2, X(x1) - X(x0), Y(y1) - Y(y0), name=name, foreign=rid)
                ctypes.add('png')
        files[f'visio/pages/page{n}.xml'] = f'{HEAD}<PageContents {NS}><Shapes>{"".join(shapes)}</Shapes></PageContents>'
        if rels:
            files[f'visio/pages/_rels/page{n}.xml.rels'] = f'{HEAD}<Relationships xmlns="{RELS}">{"".join(rels)}</Relationships>'
        page_list.append(f'<Page ID="{n - 1}" NameU="{xesc(heading[:31])}" Name="{xesc(heading[:31])}"><PageSheet>'
                         f'{_cells(PageWidth=f"{pw:.4f}", PageHeight=f"{ph:.4f}", PageScale=1, DrawingScale=1)}</PageSheet><Rel r:id="rId{n}"/></Page>')
        page_rels.append(f'<Relationship Id="rId{n}" Type="http://schemas.microsoft.com/visio/2010/relationships/page" Target="page{n}.xml"/>')
    over = ''.join(f'<Override PartName="/visio/pages/page{n}.xml" ContentType="application/vnd.ms-visio.page+xml"/>' for n in range(1, len(pages) + 1))
    files.update({
        '[Content_Types].xml': f'{HEAD}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
            + ('<Default Extension="png" ContentType="image/png"/>' if 'png' in ctypes else '')
            + '<Override PartName="/visio/document.xml" ContentType="application/vnd.ms-visio.drawing.main+xml"/>'
            '<Override PartName="/visio/pages/pages.xml" ContentType="application/vnd.ms-visio.pages+xml"/>' + over
            + '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>',
        '_rels/.rels': f'{HEAD}<Relationships xmlns="{RELS}">'
            '<Relationship Id="rId1" Type="http://schemas.microsoft.com/visio/2010/relationships/document" Target="visio/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>',
        'docProps/core.xml': f'{HEAD}<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            f'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{xesc(title)}</dc:title><dc:creator>Ward-Beck Systems</dc:creator></cp:coreProperties>',
        'docProps/app.xml': f'{HEAD}<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Microsoft Visio</Application></Properties>',
        'visio/document.xml': f'{HEAD}<VisioDocument {NS}><DocumentSettings/><Colors/><FaceNames/><StyleSheets><StyleSheet ID="0" NameU="No Style" Name="No Style">'
            + _cells(LineWeight=0.01, LineColor='#000000', LinePattern=1, FillForegnd='#FFFFFF', FillPattern=1, VerticalAlign=1)
            + '<Section N="Character"><Row IX="0"><Cell N="Size" V="0.1"/><Cell N="Color" V="#000000"/></Row></Section></StyleSheet></StyleSheets></VisioDocument>',
        'visio/_rels/document.xml.rels': f'{HEAD}<Relationships xmlns="{RELS}"><Relationship Id="rId1" '
            'Type="http://schemas.microsoft.com/visio/2010/relationships/pages" Target="pages/pages.xml"/></Relationships>',
        'visio/pages/pages.xml': f'{HEAD}<Pages {NS}>{"".join(page_list)}</Pages>',
        'visio/pages/_rels/pages.xml.rels': f'{HEAD}<Relationships xmlns="{RELS}">{"".join(page_rels)}</Relationships>',
    })
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)), data)
        for i, png in enumerate(media, 1):
            z.write(png, f'visio/media/image{i}.png')
