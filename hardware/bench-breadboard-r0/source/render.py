"""Draw the routed breadboard map as PNGs (Pillow): holes, parts, and each jumper in its net-class
colour with its number at its board end. Repository Python; reads layout.json and the routed board."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import pcb_read

SCALE = 8                 # pixels per mm
COLOURS = {'i2c': (30, 90, 220), 'wind': (20, 150, 60), 'rain': (0, 160, 190), 'charger': (230, 130, 0), 'display': (140, 60, 170),
           'power': (210, 30, 30), 'ground': (20, 20, 20)}
HOLE = (175, 175, 175)
PART = (90, 60, 140)
BACKGROUND = (250, 250, 247)
BOARD = (236, 236, 230)
BODY = (228, 222, 240)   # a breakout's overhanging board
KEY_BAND = 48             # pixels below the view for the colour key


def _font(size):
    for name in ('/System/Library/Fonts/Supplemental/Arial.ttf', '/Library/Fonts/Arial.ttf',
                 '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def draw(layout, copper, view, out, title):
    """view: (x1, y1, x2, y2) in mm. Writes out (PNG)."""
    x1, y1, x2, y2 = view
    # The view, then a band of its own for the colour key, so the key never covers a label.
    img = Image.new('RGB', (int((x2 - x1)*SCALE), int((y2 - y1)*SCALE) + KEY_BAND), BACKGROUND)
    d = ImageDraw.Draw(img)
    px = lambda x, y: ((x - x1)*SCALE, (y - y1)*SCALE)   # noqa: E731
    small, label, big = _font(int(1.6*SCALE)), _font(int(1.8*SCALE)), _font(int(2.6*SCALE))
    for b in layout['boards']:
        d.rounded_rectangle([*px(b['x1'], b['y1']), *px(b['x2'], b['y2'])], radius=12, fill=BOARD, outline=(160, 160, 150))
        d.text(px(b['x1'] + 2, b['y1'] - 4), b['label'], fill=(60, 60, 60), font=big)
    for f in layout['footprints']:
        for h in f['holes']:
            cx, cy = px(h['x'], h['y'])
            d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=HOLE)
    for part in layout['parts']:   # a breakout's board overhangs: no wire goes under it
        if part.get('body'):
            d.rectangle([*px(*part['body'][:2]), *px(*part['body'][2:])], fill=BODY, outline=(170, 150, 200), width=2)
    for part in layout['parts']:
        d.rectangle([*px(*part['box'][:2]), *px(*part['box'][2:])], outline=PART, width=3)
        for x, y in part['pins'].values():
            cx, cy = px(x, y)
            d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=PART)
    for t in layout['labels']:   # left-aligned 6 mm before x, or centred on x
        x, y = px(t['x'] - (0 if t.get('centre') else 6), t['y'] - 1.5)
        if t.get('centre'):
            x -= d.textlength(t['text'], font=small)/2
        d.text((x, y), t['text'], fill=(60, 60, 60), font=small)
    for j in layout['jumpers']:
        colour = COLOURS[j['class']]
        segments = ([(j['a'], j['b'], None)] if j.get('flying')   # between boards: straight, as it hops over
                    else copper.get(j['id'], {'segments': []})['segments'])
        for p, q, _layer in segments:
            d.line([*px(*p), *px(*q)], fill=colour, width=4)
        for end in (j['a'], j['b']):
            cx, cy = px(*end)
            d.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], outline=colour, width=3)
    placed = []
    for j in layout['jumpers']:   # labels last, over every wire, at the end on a breadboard
        x, y = j['a'] if not j['a_name'].startswith('NUCLEO') else j['b']
        cx, cy = px(x, y)
        width = d.textlength(j['id'], font=small)
        for ox, oy in ((7, -22), (7, 6), (-width - 9, -22), (-width - 9, 6), (7, -40), (-width - 9, 24)):
            box = d.textbbox((cx + ox, cy + oy), j['id'], font=small)
            box = (box[0] - 2, box[1] - 1, box[2] + 2, box[3] + 1)
            if not any(box[0] < q[2] and q[0] < box[2] and box[1] < q[3] and q[1] < box[3] for q in placed):
                break
        placed.append(box)
        d.rectangle(box, fill=(255, 255, 255))
        d.text((box[0] + 2, box[1] + 1 - (d.textbbox((0, 0), j['id'], font=small)[1])), j['id'],
               fill=COLOURS[j['class']], font=small)
    for part in layout['parts']:   # part names over the wires too
        pos = px(part['label_x'], part['label_y'] - 1.4)
        box = d.textbbox(pos, part['id'], font=label)
        d.rectangle([box[0] - 2, box[1] - 1, box[2] + 2, box[3] + 1], fill=(255, 255, 255))
        d.text(pos, part['id'], fill=PART, font=label)
    d.text((10, 10), title, fill=(30, 30, 30), font=big)
    key = 10
    for name, colour in COLOURS.items():
        d.line([key, img.height - 24, key + 40, img.height - 24], fill=colour, width=6)
        d.text((key + 46, img.height - 38), name, fill=(30, 30, 30), font=small)
        key += 46 + int(d.textlength(name, font=small)) + 30
    img.save(out, optimize=False)


def render_all(layout, pcb, outdir):
    copper = pcb_read.copper_by_net(pcb)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    full = layout['outline']
    boards = {b['id']: b for b in layout['boards']}
    for bid, name in (('A', 'board-a.png'), ('B', 'board-b.png'), ('C', 'board-c.png')):
        b = boards[bid]
        top = min([b['y1']] + [p['body'][1] for p in layout['parts'] if p['board'] == bid and p.get('body')])
        draw(layout, copper, (b['x1'] - 8, top - 14, b['x2'] + 8, b['y2'] + 8), outdir/name,
             f'Bench breadboard map, {b["label"]} (jumpers to the NUCLEO continue in overview.png)')
    top = min([full[1]] + [p['body'][1] for p in layout['parts'] if p.get('body')])
    draw(layout, copper, (full[0], top - 14, full[2], full[3] + 6), outdir/'overview.png',
         'Bench breadboard map: the three boards and the NUCLEO-WL55JC1 headers (not to scale)')
