"""Turn layout.json (make.py) into an unrouted KiCad 10 board. Run with KiCad's own Python:

    <KiCad.app>/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 build_pcb.py layout.json out.kicad_pcb

Each breadboard is one footprint whose pads are its holes; the NUCLEO headers are another. A pad
has a jumper's net (W1, W2, ...) if a jumper ends there, else no net: the router routes each jumper
between its two pads and steers around every other hole. The parts and boards are silkscreen outlines
with their names; off the breadboard (record D2), each lever connector (joint) is an outline with its id
and kind and its numbered positions, and each part placed by place_mm is its outline with its id. The
leads carry no copper: they are drawn by render.py and in the 3D view."""
import itertools
import json
import sys
import uuid

import pcbnew as k

PAD = 1.2      # mm, round through-hole pad
DRILL = 0.8    # mm
SILK = 0.15    # mm line width
TEXT = 1.0     # mm text height


_count = itertools.count()


def stamp(item):
    """A UUID from a running count: KiCad orders a saved board by UUID, so random ones would
    reorder the file on every build."""
    item.SetUuid(k.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL, f'bench-breadboard-r0/item/{next(_count)}'))))
    return item


def xy(x, y):
    return k.VECTOR2I(k.FromMM(x), k.FromMM(y))


def footprint(board, ref, holes, nets):
    f = stamp(k.FOOTPRINT(board))
    f.SetReference(ref)
    f.SetValue(ref)
    f.Reference().SetVisible(False)
    f.Value().SetVisible(False)
    f.SetAttributes(k.FP_THROUGH_HOLE)
    for h in holes:
        p = stamp(k.PAD(f))
        p.SetNumber(h['name'])
        p.SetShape(k.PAD_SHAPE_CIRCLE)
        p.SetAttribute(k.PAD_ATTRIB_PTH)
        p.SetSize(xy(PAD, PAD))
        p.SetDrillSize(xy(DRILL, DRILL))
        p.SetLayerSet(k.PAD.PTHMask())
        p.SetPosition(xy(h['x'], h['y']))
        if h.get('net'):
            p.SetNet(nets[h['net']])
        f.Add(p)
    board.Add(f)


def rect(board, x1, y1, x2, y2, layer, width):
    s = stamp(k.PCB_SHAPE(board))
    s.SetShape(k.SHAPE_T_RECT)
    s.SetStart(xy(x1, y1))
    s.SetEnd(xy(x2, y2))
    s.SetLayer(layer)
    s.SetWidth(k.FromMM(width))
    board.Add(s)


def text(board, value, x, y, size=TEXT):
    t = stamp(k.PCB_TEXT(board))
    t.SetText(value)
    t.SetPosition(xy(x, y))
    t.SetTextSize(xy(size, size))
    t.SetTextThickness(k.FromMM(SILK))
    t.SetLayer(k.F_SilkS)
    board.Add(t)


def main(layout_path, out):
    layout = json.loads(open(layout_path).read())
    board = k.BOARD()
    board.SetCopperLayerCount(2)
    nets = {}
    for name in layout['jumper_nets']:
        nets[name] = k.NETINFO_ITEM(board, name)
        board.Add(nets[name])
    for group in layout['footprints']:
        footprint(board, group['ref'], group['holes'], nets)
    for b in layout['boards']:
        rect(board, b['x1'], b['y1'], b['x2'], b['y2'], k.F_SilkS, SILK)
        text(board, b['label'], b['x1'] + 6, b['y1'] - 2, 1.5)
    for part in layout['parts']:
        rect(board, *part['box'], k.F_SilkS, SILK)
        text(board, part['id'], part['label_x'], part['label_y'])
    for joint in layout.get('joints', []):
        rect(board, *joint['box'], k.F_SilkS, SILK)
        text(board, f"{joint['id']} ({joint['kind']})", joint['label_x'], joint['label_y'])
        for n, (x, y) in enumerate(joint['xy'], start=1):
            text(board, str(n), x, y, 0.8)
    for label in layout['labels']:
        text(board, label['text'], label['x'], label['y'], label.get('size', TEXT))
    rect(board, *layout['outline'], k.Edge_Cuts, 0.1)
    k.SaveBoard(out, board)


def add_models(pcb, view_path, out):
    """The 3D view: the routed board with a padless footprint for each 3D model (view.json)."""
    board = k.LoadBoard(pcb)
    for m in json.loads(open(view_path).read()):
        f = stamp(k.FOOTPRINT(board))
        f.SetReference(m['ref'])
        f.SetValue(m['ref'])
        f.Reference().SetVisible(False)
        f.Value().SetVisible(False)
        f.SetAttributes(k.FP_EXCLUDE_FROM_BOM | k.FP_EXCLUDE_FROM_POS_FILES)
        f.SetPosition(xy(m['x'], m['y']))
        for spec in m['models']:
            model = k.FP_3DMODEL()
            model.m_Filename = spec['file']
            model.m_Offset = k.VECTOR3D(spec.get('dx', 0), spec.get('dy', 0), spec['z'])
            model.m_Rotation = k.VECTOR3D(0, 0, spec['rot'])
            f.Add3DModel(model)
        board.Add(f)
    k.SaveBoard(out, board)


if __name__ == '__main__':
    if sys.argv[1] == '--add-models':
        add_models(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        main(sys.argv[1], sys.argv[2])
