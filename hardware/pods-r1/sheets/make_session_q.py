"""Session Q: the printed pod boxes, the shield and the install. Session P's flat-pack style and pipeline (pods_sheet.py):
illustrations rendered from real 3D geometry by scenes_q.py (svg/*.svg + anchors in svg/*.json; the boxes from
box/podbox.py, the shield from shield/assemble.py + shield/remix.py through mrender.py), every label on a paper chip
whose leader stops at the chip edge, and the TX label-overlap and hole-callout checks run on every page.

Source of truth (read-only): box/podbox.py (every box, bore, opening, groove, the window), shield/remix.py (the cap's
and the arm's mount holes, the lead holes, the fitting order), shield/assemble.py (the shield stack, the SHT45 on the
stand), layout/pods.py (the boards, J1, U1's WP, JP1), sources.py (screws, inserts, the gland, the cord, the window).

The shield's meshes have no known licence: this PDF and the scene SVGs stay in the gitignored out/ and svg/ folders.

Usage: $PDFPY make_session_q.py OUT_DIR      (render first: sh render_q.sh; or sh build_q.sh)
Writes OUT_DIR/session-q-install.pdf and OUT_DIR/session-q-manifest.json; exits non-zero on any label or hole issue.
"""
import json
import sys
from pathlib import Path

SHEETS_DIR = Path(__file__).resolve().parent
PODS = SHEETS_DIR.parent
REPO = PODS.parent.parent
TXS = REPO / "hardware" / "tx-stack-r1" / "sheets"
for p in (SHEETS_DIR, TXS / "session3", TXS / "session1" / "v2", PODS / "layout", PODS / "box", PODS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
sys.dont_write_bytecode = True

from pods_sheet import *        # noqa: F401,F403,E402  (sheetlib's page furniture + the pods' shared page helpers)
import pods_sheet as PS         # noqa: E402,F401
import sheetlib as SL           # noqa: E402
import pods as PD               # noqa: E402
import sources as S             # noqa: E402

SL.SVG = SHEETS_DIR / "svg"
SL.PROTO = "PROTOCOL Q // SESSION Q // BOXES + SHIELD + INSTALL"
SL.LEADER_INK = True
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else SHEETS_DIR / "out"

POD = ("TH", "BARO", "UV")
LID_SCREW = S.val("pod_screw")                       # (3.0, 8.0, 5.5)
MOUNT_SCREW = S.val("pod_mount_screw")               # (3.0, 10.0, 5.5)
INS_L, INS_D = S.val("insert_m3")
BORE_D, BORE_DEPTH = S.val("pod_insert_bore")
CORD = S.val("pod_oring")
WIN_MAT, WIN_D, WIN_T = S.val("uv_window")
EPTFE_D, EPTFE_T = S.val("baro_eptfe")
SEAL_LO, SEAL_HI = S.val("pg7_seal")
GLAND_HOLE = S.val("th_lead_gland")[0]
M8 = f"M3 x {LID_SCREW[1]:g}"
M10 = f"M3 x {MOUNT_SCREW[1]:g}"


def _box_facts():
    """Per-pod numbers read from box/podbox.py (needs .venv-cad's CadQuery for the groove's length; the build runs on
    .venv-pdf, so scenes_q.py's render writes them to svg/q_facts.json)."""
    return json.load(open(SL.SVG / "q_facts.json"))


FACTS = _box_facts()
SLOGANS_Q = [
    "THREE BOXES. EIGHT INSERTS EACH. ONE SHIELD.",
    "THE RIM TAKES THE LID. THE BACK TAKES THE SHIELD.",
    "HOT BRASS, STRAIGHT DOWN, FLUSH. ONCE.",
    "THE SEAL GOES OUTSIDE. THE LOCKNUT GOES INSIDE.",
    "THREAD THE LEAD BEFORE YOU SOLDER IT. AGAIN.",
    "SHUNT ON. BEEP. THEN CLOSE THE LID.",
    "THE LID LANDS ON PLASTIC. STOP TURNING.",
    "WATER FOLLOWS THE CABLE. THE LOOP SENDS IT DOWN.",
]
POD_WORD = {"TH": "TH (SHT45 TEMPERATURE + HUMIDITY)", "BARO": "BARO (BMP581 PRESSURE)", "UV": "UV (LTR390)"}


# ------------------------------------------------------------------ small helpers
def L(c, a, items, size=8.5, pad=-2):
    """Chips for named anchors: items [(text, anchor, lane)]."""
    lanes(c, [(t, *a.A(n), ln, False) for t, n, ln in items], art_box(a, pad), size=size)


def LH(c, a, items, size=8.5, pad=2):
    """Ring each hole anchor and chip it: items [(text, anchor, lane)]."""
    its = []
    for t, n, ln in items:
        px, py = a.A(n)
        ring(c, px, py)
        its.append((t, px, py, ln, True))
    lanes(c, its, art_box(a, pad), size=size)


def seen(code, mirrored):
    """A lug's corner code (B/T = gland end / far end; L/R in the box frame) as it reads on a drawing."""
    lr = code[1]
    if mirrored:
        lr = {"L": "R", "R": "L"}[lr]
    return ("GLAND END" if code[0] == "B" else "FAR END") + ", " + ("LEFT" if lr == "L" else "RIGHT")


def rows_table(c, x, ytop, w, head, rows, size=8.4, col=None, ticks=False, lead=11.0):
    """A plain table: head [(text, x offset)], rows [[cell, ...]] with the same offsets. Returns the y under it."""
    col = col or [h[1] for h in head]
    for t, dx in head:
        text(c, x + dx, ytop, t, 8, "MONO", GREY)
    yy = ytop - 15
    for r in rows:
        nl = 1
        for k, cell in enumerate(r):
            right = (col[k + 1] if k + 1 < len(col) else w - (24 if ticks else 4)) - col[k] - 6
            lines = wrap_px(cell, right, size)
            nl = max(nl, len(lines))
            for j, ln in enumerate(lines):
                text(c, x + col[k], yy - j * lead, ln, size, "HEAD" if k == 0 else "ALT", INK)
        if ticks:
            tick_box(c, x + w - 18, yy - 3, 12)
        yy -= nl * lead + 7
    LAB.block(x, yy + 4, x + w, ytop + 9, "table")
    return yy


# ------------------------------------------------------------------ the pages
PAGES = []          # (step, title, tags, fn)


def add_page(step, title, tags, fn):
    PAGES.append((step, title, tags, fn))


def cover(c, pg):
    page(c, "00", "SESSION Q: BOXES, SHIELD, INSTALL",
         "THE 3 PRINTED POD BOXES CLOSED AND SEALED, THEN ON THE REMIXED SHIELD. BOARDS FROM SESSION P.", pg, SLOGANS_Q[0])
    g = Grid(1, 1)
    x, y, w, h = panel(c, g.cell(0, 0), None, cap(
        "PARTS AS SUPPLIED. Printed parts as they come off the bed; the gland as it comes in its bag (body, seal, dome nut,",
        "locknut, all assembled); inserts, screws, cord and ties loose. Quantities are for all three pods.", width=100))
    n_ins = sum(f["inserts"] for f in FACTS.values())
    cord_m = sum(f["groove"] for f in FACTS.values()) / 1000
    items = [("TH BOX (PETG): BODY + LID\n2 GLAND HOLES, BOTTOM WALL", "q_p_box_th"),
             ("BARO BOX (PETG): BODY + LID\nGLAND HOLE + VENT, BOTTOM WALL", "q_p_box_baro"),
             ("UV BOX (PETG): BODY + LID\nFLOOR GLAND HOLE, LID WINDOW", "q_p_box_uv"),
             (f"M3 HEAT-SET INSERT ({n_ins}x)\n{INS_L:g} LONG, {INS_D:g} KNURL (TBD)", "q_p_insert"),
             ("PG-7 #762 GLAND (4x): 1 PER BOX\n+ TH'S 2ND, FOR THE SHT45 LEAD", "q_p_gland"),
             (f"O-RING CORD {CORD:g} MM, NBR/EPDM\n{cord_m:.1f} M + SPARE (3 LIDS)", "q_p_cord"),
             (f"{M8} PAN HEAD (18x)\n12 LID + 6 BOARD", "q_p_m3x8"),
             (f"{M10} PAN HEAD (12x)\n4 PER BOX, INTO THE SHIELD", "q_p_m3x10"),
             (f"UV WINDOW: PTFE DISC {WIN_D:g} x {WIN_T:g}\n+ BARO ePTFE PATCH {EPTFE_D:g} (OPTIONAL)", "q_p_window"),
             ("UV-RESISTANT CABLE TIES\n2 FOR THE SHT45 + CABLE TIES", "q_p_tie"),
             ("REMIXED TOP CAP (WHITE)\nUV BOX SADDLE + LUG BOSSES", "q_p_cap"),
             ("REMIXED L-ARM (WHITE)\nTH + BARO FACES, LEAD HOLE", "q_p_arm")]
    cw, rh = w / 3, h / 4
    for i, (name, art) in enumerate(items):
        col, row = i % 3, i // 3
        X, Y = x + cw * col, y + h - rh * (row + 1)
        Art(c, art, X + 10, Y + 34, cw - 20, rh - 42)
        chip(c, X + cw / 2, Y + 18, name, 7.6, "ALT", INK, "c")


def before(c, pg):
    page(c, "00", "BEFORE YOU START", "TOOLS, THE ORDER OF THE STEPS, AND HOW THIS SHEET NAMES EVERY FACE AND HOLE.", pg,
         SLOGANS_Q[1])
    g = Grid(2, 2, heights=[1.3, 1])
    x, y, w, h = panel(c, g.cell(0, 0), None, "TOOLS AND CONSUMABLES.")
    tools = ["SOLDERING IRON + AN M3 HEAT-SET INSERT TIP", "  (OR AN OLD CONICAL TIP YOU DON'T NEED)",
             "PH1 CROSS SCREWDRIVER (THE M3 PAN HEADS)", "SPANNER OR PLIERS FOR THE PG-7 NUTS",
             "SHARP KNIFE + STEEL RULER (THE CORD)", "INSTANT GLUE (CYANOACRYLATE): CORD JOINT",
             "NEUTRAL-CURE SILICONE (UV WINDOW)", "MULTIMETER: CONTINUITY (SHUNT CHECK)",
             "FLUSH CUTTERS (CABLE TIE TAILS)", "ISOPROPYL ALCOHOL + CLOTH"]
    for i, s in enumerate(tools):
        text(c, x + 12, y + h - 16 - i * 14.5, ("-  " if not s.startswith(" ") else "   ") + s.strip(), 8.6, "ALT", INK)
    x, y, w, h = panel(c, g.cell(1, 0), None, "THE STEPS. IN THIS ORDER.")
    for i, (n, s) in enumerate(STEP_LIST):
        text(c, x + 12, y + h - 14 - i * min(14.5, (h - 20) / len(STEP_LIST)), f"{n}  {s}", 8.0, "HEAD", INK)
    x, y, w, h = panel(c, g.cell(0, 1, 2), None, "STANDING ORDERS.", warn=True)
    rules = ["EVERY BOX HAS A RIM (THE OPEN SIDE THE LID SCREWS TO) AND A BACK FACE (FLAT, CLOSED: THE MOUNT FACE, ON THE "
             "SHIELD). TH AND BARO ALSO HAVE A BOTTOM WALL: THE SHORT WALL WITH THE GLAND HOLES.",
             "THE UV BOX'S GLAND HOLE IS IN ITS BACK FACE: ON THE CAP THAT FACE IS ITS FLOOR. ITS LID CARRIES THE WINDOW.",
             "CORNERS ARE NAMED GLAND END / FAR END, LEFT / RIGHT AS DRAWN. EACH OF THE 4 CORNER LUGS HAS TWO BORES: ONE "
             "FROM THE RIM (LID SCREW), ONE FROM THE BACK FACE (MOUNT SCREW). THEY DO NOT MEET.",
             f"SCREWS: {M8} INTO THE LID INSERTS AND THE BOARD STANDOFFS. {M10} ONLY THROUGH THE SHIELD INTO THE BACK INSERTS.",
             "THE BOARDS, THE PORT CABLES AND THE TH LEAD ARE SESSION P. THIS SHEET SAYS WHEN TO GO BACK TO IT.",
             "NO POWER IN THIS SESSION. ANYTHING THAT WILL NOT FIT: STOP, PHOTOGRAPH IT, REPORT TO CLAUDE. NO FILING."]
    for i, s in enumerate(rules):
        yy = y + h - 12 - i * (h - 8) / len(rules)
        verdict(c, x + 18, yy, True, 7)
        for k, ln in enumerate(wrap_px(s, w - 44, 8.0)):
            text(c, x + 32, yy - 3 - k * 9.3, ln, 8.0, "ALT", INK)


def faces(c, pg):
    page(c, "01", "KNOW THE THREE BOXES", "EACH BOX: BODY + LID. FIND THE RIM, THE BACK FACE AND THE GLAND HOLES "
         "BEFORE ANY HEAT GOES IN.", pg, SLOGANS_Q[1])
    g = Grid(3, 2)
    for k, name in enumerate(POD):
        p = name.lower()
        for row, view in enumerate(("front", "back")):
            if row == 0:
                cp = {"TH": ["TH: from the rim. Two gland", "holes in the bottom wall."],
                      "BARO": ["BARO: from the rim. One gland", "hole + the small vent."],
                      "UV": ["UV: flat and shallow. From the", "rim: two bosses on the floor."]}[name]
            else:
                cp = {"TH": ["TH: the back face (flat, no", "holes): the mount face."],
                      "BARO": ["BARO: the back face. Same", "shape as TH, a bit bigger."],
                      "UV": ["UV: the back face = the floor.", "Its gland hole is in it."]}[name]
            x, y, w, h = panel(c, g.cell(k, row), k + 1 + 3 * row, cp)
            a = Art(c, f"q_face_{p}_{view}", x + 14, y + 22, w - 28, h - 64)
            if view == "front":
                its = [("RIM (LID)", "rim", "up"), ("LUG", "lug", "up")]
                if name == "UV":
                    its.append(("END WALL", "end", "dn"))
                else:
                    its.append(("BOTTOM WALL", "bottom", "dn"))
            else:
                its = [("BACK FACE", "back", "up"), ("LUG", "lug", "dn" if name == "UV" else "up")]
                if name == "UV":
                    its.append(("GLAND HOLE", "op:gland", "dn"))
                else:
                    its.append(("BOTTOM WALL", "bottom", "dn"))
            L(c, a, its, size=8.0)


def inserts_page(name, step):
    p = name.lower()

    def f(c, pg):
        fx = FACTS[name]
        page(c, step, f"{name} BOX: {fx['inserts']} HEAT-SET INSERTS",
             f"4 FROM THE RIM (LID SCREWS), {fx['inserts'] - 4} FROM THE BACK FACE (MOUNT SCREWS). BORES "
             f"{BORE_D:g} ACROSS, {BORE_DEPTH:g} DEEP.", pg, SLOGANS_Q[2])
        g = Grid(2, 2, heights=[1.25, 1])
        x, y, w, h = panel(c, g.cell(0, 0), 1, ["RIM UP. The 4 rim bores, one in each", "corner lug: the lid's screws.",
                                                "Insert 1 into each (step 3)."])
        a = Art(c, f"q_ins_{p}_rim", x + 10, y + 26, w - 20, h - 56)
        rim = sorted((n for n in a.holes if n.startswith("rim:")))
        LH(c, a, [(seen(n[4:], False), n, "up" if n[4] == "T" else "dn") for n in rim], size=8.0)
        if name == "UV":
            cp = ["BACK FACE UP (box turned over). 2 lug", "bores at the FAR END + 2 in the floor",
                  "bosses (inside the box, blind). Mount screws."]
        else:
            cp = ["BACK FACE UP (box turned over). The", "same 4 lugs, the other end: 4 back bores.",
                  "Blind: they never reach the rim bores."]
        x, y, w, h = panel(c, g.cell(1, 0), 2, cp)
        b = Art(c, f"q_ins_{p}_back", x + 10, y + 26, w - 20, h - 56)
        back = sorted(n for n in b.holes)
        its = []
        for n in back:
            if n.startswith("back:"):
                its.append((seen(n[5:], True), n, "up" if n[5] == "T" else "dn"))
            else:
                its.append(("FLOOR BOSS " + ("RIGHT" if n.endswith("L") else "LEFT"), n, "dn"))
        LH(c, b, its, size=8.0)
        x, y, w, h = panel(c, g.cell(0, 1), 3, ["3  One corner lug, close up: the insert", "over its rim bore, chamfered end DOWN.",
                                                "Same at every bore, rim and back."])
        a = Art(c, f"q_ins_{p}_lug", x + 20, y + 22, w - 40, h - 46)
        L(c, a, [("INSERT: CHAMFER DOWN", "ins", "up"), ("BORE", "bore", "dn"), ("CORNER LUG", "lug", "dn")], size=8.0)
        x, y, w, h = panel(c, g.cell(1, 1), 4, ["Check every one: flush (a straight edge", "rocks on none), square, and an",
                                                "M3 screw turns in by hand."], warn=True)
        yy = para(c, x + 40, y + h - 14, wrap_px(
            "Iron at PETG heat (about 230 C) with the insert tip. Insert on the tip, its SMALL (chamfered) end into the bore. "
            "Press straight down, slowly, no twisting, until its top is FLUSH with the face. Lift the iron straight off; "
            "hold a flat steel part on the insert 10 s while it sets. Rim bores with the rim up; back bores with the back up.",
            w - 52, 8.6), 8.6, 11.5, w=w - 44, what="insert method")
        para(c, x + 12, yy - 8, wrap_px(
            f"{fx['inserts']} inserts in the {name} box. A crooked insert: heat it, pull it with pliers, let the bore cool, "
            "and put a new one in. A bore that has gone oversize: stop, photograph it, report to Claude. The insert size "
            f"({INS_L:g} long, {INS_D:g} knurl) is TBD: measure yours. Each bore is {BORE_D:g} across x {BORE_DEPTH:g} deep, "
            "so a longer insert stands proud: stop.", w - 26, 8.2), 8.2, 10.5, color=GREY, w=w - 20, what="insert notes")
    return f


def gland_supplied(c, pg):
    page(c, "05", "THE PG-7 #762 AS SUPPLIED", "BODY + SEAL RING + DOME NUT + LOCKNUT, ALL SCREWED TOGETHER. "
         "TAKE THE LOCKNUT OFF.", pg, SLOGANS_Q[3])
    g = Grid(1, 2, heights=[1, 1])
    x, y, w, h = panel(c, g.cell(0, 0), 1, cap(
        "AS SUPPLIED (drawn from the side): the gland comes assembled. Dome nut (the domed cap: it squeezes the seal",
        "round the cable), hex body, the flat rubber SEAL RING on the thread against the hex, then the LOCKNUT on the",
        "thread's end. Same for all 4.", width=100))
    a = Art(c, "q_gland_sup", x + 90, y + 20, w - 180, h - 60)
    L(c, a, [("DOME NUT", "dome", "up"), ("HEX BODY", "hex", "up"), ("SEAL RING", "seal", "up"),
             ("LOCKNUT", "lock", "up")])
    x, y, w, h = panel(c, g.cell(0, 1), 2, cap(
        "Unscrew the LOCKNUT off the thread and keep it with its gland. Leave the dome nut on, LOOSE (two turns back), and",
        "the seal ring on the thread against the hex. The thread goes through the box wall from OUTSIDE; the locknut goes",
        f"on from INSIDE. Each hole is {GLAND_HOLE:g} across. Seals cables {SEAL_LO:g}-{SEAL_HI:g} mm across.", width=100))
    a = Art(c, "q_gland_off", x + 40, y + 20, w - 80, h - 60)
    L(c, a, [("DOME NUT: LOOSE", "dome", "up"), ("SEAL RING: STAYS", "seal", "up"), ("THREAD", "thread", "dn"),
             ("LOCKNUT: OFF", "lock", "up")])


def gland_page(name, step):
    p = name.lower()

    def f(c, pg):
        if name == "TH":
            title, sub = "TH BOX: TWO GLANDS", "PORT-CABLE GLAND + THE SHT45 LEAD'S GLAND, BOTH IN THE BOTTOM WALL."
        elif name == "BARO":
            title, sub = "BARO BOX: GLAND + VENT", "ONE GLAND IN THE BOTTOM WALL. THE VENT HOLE STAYS OPEN: NEVER TAPE IT."
        else:
            title, sub = "UV BOX: THE FLOOR GLAND", "ONE GLAND, IN THE BACK FACE (THE FLOOR ON THE CAP). LOCKNUT INSIDE."
        page(c, step, title, sub, pg, SLOGANS_Q[3])
        g = Grid(2, 2, heights=[1.15, 0.85] if name == "UV" else [0.8, 1.2])
        if name == "TH":
            cp = ["The bottom wall from outside. Port-cable", "hole (left, as drawn) and the lead's hole",
                  "(right). The pointed tops are print", "teardrops: leave them, the seal covers them."]
        elif name == "BARO":
            cp = ["The bottom wall from outside: the gland", "hole and the 4 mm vent. The pointed top is",
                  "a print teardrop: the seal covers it."]
        else:
            cp = ["The back face (floor) from outside: the", "gland hole at the gland end, past the two",
                  "floor-boss inserts (step 04)."]
        x, y, w, h = panel(c, g.cell(0, 0), 1, cp)
        a = Art(c, f"q_gl_{p}_holes", x + 10, y + 22, w - 20, h - 50)
        its = [("PORT-CABLE GLAND HOLE" if name != "UV" else "GLAND HOLE", "op:gland", "up")]
        if name == "TH":
            its.append(("LEAD GLAND HOLE", "op:lead_gland", "dn"))
        if name == "BARO":
            its.append(("VENT 4 MM", "op:vent", "dn"))
        L(c, a, its)
        if name == "UV":
            cp2 = ["1  Thread up through the floor from", "OUTSIDE, seal ring on the outside face.",
                   "2  Inside: locknut on, hand tight + 1/4.", "Dome nut stays loose for the cable."]
        else:
            cp2 = ["1  Thread in from OUTSIDE, seal ring", "against the outside face. 2  Inside: the",
                   "locknut on, hand tight, then 1/4 turn", "with the spanner. Dome nuts stay loose."]
        x, y, w, h = panel(c, g.cell(1, 0), 2, cp2)
        a = Art(c, f"q_gl_{p}_in", x + 10, y + 22, w - 20, h - 50)
        its = [("LOCKNUT INSIDE", "lock:gland", "up")]
        if name == "TH":
            its.append(("LEAD GLAND'S LOCKNUT", "lock:lead_gland", "up"))
        if name == "BARO":
            its += [("ePTFE PATCH (OPTIONAL)", "eptfe", "dn"), ("BAFFLE FIN", "baffle", "dn")]
        L(c, a, its)
        if name == "TH":
            cp3 = cap("Done, from outside. The PORT CABLE goes through the PORT-CABLE gland (the higher one, under J1's mouth);",
                      "the SHT45 LEAD through the LEAD gland (step 10). Both dome nuts stay loose until their cable is in.",
                      width=100)
        elif name == "BARO":
            cp3 = cap("Done, from outside. Inside, a fin (the BAFFLE) stands over the vent: no straight line in to the BMP581.",
                      f"OPTIONAL: an adhesive ePTFE vent patch ({EPTFE_D:g} across) goes in the round seat on the INSIDE face,",
                      "over the vent, before the board goes in. No patch on hand: leave the seat empty. Never tape the vent.",
                      width=100)
        else:
            cp3 = cap("Done, from below. On the cap this gland hangs past the saddle in its notch (step 20); the cable comes",
                      "up through it into the box and bends over into the jack. Dome nut loose until the cable is in.",
                      width=100)
        x, y, w, h = panel(c, g.cell(0, 1, 2), 3, cp3)
        a = Art(c, f"q_gl_{p}_out", x + 60, y + 24, w - 120, h - 52)
        its = [("DOME NUT: LOOSE", "dome:gland", "lt")]
        if name == "TH":
            its[0] = ("PORT-CABLE GLAND", "dome:gland", "lt")
            its.append(("LEAD GLAND", "dome:lead_gland", "rt"))
        if name == "BARO":
            its.append(("VENT: OPEN", "op:vent", "rt"))
        L(c, a, its)
    return f


def window_page(c, pg):
    page(c, "09", "UV LID: THE WINDOW", f"PTFE DISC {WIN_D:g} x {WIN_T:g} INTO THE RECESS IN THE LID'S TOP FACE, "
         "FLUSH, BEDDED IN SILICONE.", pg, SLOGANS_Q[3])
    g = Grid(2, 1)
    x, y, w, h = panel(c, g.cell(0, 0), 1, cap(
        "The UV LID, top face up (the face WITHOUT the groove). The recess is", f"{WIN_D + 0.3:g} across, {WIN_T:g} deep, over a "
        f"{WIN_D - 3:g} aperture. 1  Wipe the", "recess and the disc with alcohol. 2  A thin bead of neutral-cure",
        "silicone round the recess's ledge (not on the aperture). 3  Press", "the disc in until FLUSH with the lid; "
        "wipe the squeeze-out off the", "top. 4  Lid flat, 24 h to cure, before step 16.", width=48))
    a = Art(c, "q_win_iso", x + 6, y + 30, w - 12, h - 70)
    L(c, a, [("PTFE DISC", "disc", "up"), ("RECESS + LEDGE", "recess", "up"), ("APERTURE", "aperture", "up")])
    x, y, w, h = panel(c, g.cell(1, 0), 2, cap(
        "Done, from above. The disc sits flush: no lip for water to pond on. It sits over the LTR390 when the lid is on:",
        "the window is at the lid's FAR END, away from the gland end.", f"Disc: {WIN_MAT}; TBD, measure yours.", width=48),
        warn=True)
    a = Art(c, "q_win_top", x + 30, y + 30, w - 60, h - 70)
    L(c, a, [("WINDOW, FLUSH", "disc", "up"), ("UV LID", "lid", "dn")])


def lead_page(c, pg):
    page(c, "10", "TH: THE SHT45 LEAD, CUP + ARM + GLAND", "ITS BARE POD END DOWN THROUGH 3 HOLES; THEN SESSION P "
         "STEP 11 SOLDERS IT.", pg, SLOGANS_Q[4])
    g = Grid(2, 2, heights=[1, 1])
    c0, c1 = g.cell(0, 0), g.cell(0, 1)
    tall = (c1[0], c1[1], c1[2], c0[1] + c0[3] - c1[1])
    x, y, w, h = panel(c, tall, 1, cap(
        "The route, on the arm from the front (the cup's", "stand side up, BARO's face on the left): the SHT45",
        "stays up on the stand; its lead runs down through", "the BASE CUP's own 5 mm hole, out under the cup's",
        "disc, down through the ARM's 6 mm lead hole, down", "the inside of the TH face, under its bottom edge",
        "and UP into the TH box's LEAD GLAND: a drip loop.", "Thread it now, cup and arm in your hands. The",
        "boxes go on the arm at step 18, the cup at 19.", width=50))
    a = Art(c, "q_lead_iso", x + 14, y + 26, w - 28, h - 56)
    L(c, a, [("1 CUP: 5 MM HOLE", "cuphole", "up"), ("2 ARM: 6 MM LEAD HOLE", "armhole", "dn"),
             ("3 LEAD GLAND", "gland", "dn"), ("DRIP LOOP", "loop", "dn")], size=8.0)
    x, y, w, h = panel(c, g.cell(1, 0), 2, ["1  The BASE CUP from above: the bare", "end down through its 5 mm hole,",
                                            "from the disc (stand) side."])
    a = Art(c, "q_lead_cup", x + 20, y + 22, w - 40, h - 50)
    LH(c, a, [("5 MM HOLE", "cuphole", "up")], pad=2)
    L(c, a, [("CUP DISC", "disc", "dn")])
    x, y, w, h = panel(c, g.cell(1, 1), 3, ["2  The ARM from below: down through its", "6 mm lead hole in the TH tab. 3  Into",
                                            "the TH box's LEAD gland: its DOME NUT", "first, then up through the gland body."],
                       warn=True)
    a = Art(c, "q_lead_arm", x + 20, y + 22, w - 40, h - 50)
    LH(c, a, [("6 MM LEAD HOLE", "armhole", "up")], pad=2)
    L(c, a, [("TH FACE", "thface", "dn")])


def bib_page(name, step):
    p = name.lower()

    def f(c, pg):
        page(c, step, f"{name} BOARD INTO THE {name} BOX", f"2 x {M8} THROUGH THE PERMA-PROTO'S MOUNTING HOLES "
             "INTO THE STANDOFFS. THEN THE PLUG INTO J1.", pg, SLOGANS_Q[4])
        g = Grid(2, 1)
        pre = {"TH": "Session P done for TH, including step 11 (the lead's pod end, through its gland, soldered).",
               "BARO": "Session P done for BARO, its port cable through its gland and crimped (Session P C1-C2).",
               "UV": "Session P done for UV, its port cable up through the FLOOR gland and crimped (Session P C1-C2)."}[name]
        x, y, w, h = panel(c, g.cell(0, 0), 1, cap(
            pre, "1  Board in, top face up (print readable), J1's mouth toward the gland end. 2  A screw through each",
            "mounting hole into its standoff: thread-forming into the plastic, snug, no more. 3  Plug the port cable's",
            "plug into J1 until it clicks. 4  Leave a little slack, then tighten the dome nut by hand + 1/4 turn.",
            width=48))
        a = Art(c, f"q_bib_{p}_top", x + 70, y + 20, w - 140, h - 40)
        its = [(f"{M8}", "bscrew0", "lt"), (f"{M8}", "bscrew1", "rt"), ("PLUG IN J1", "plug", "lt"),
               ("PORT CABLE", "cable", "lt")]
        if name == "TH":
            its.append(("SHT45 LEAD", "L:out", "rt"))
        L(c, a, its, size=8.0)
        x, y, w, h = panel(c, g.cell(1, 0), 2, cap(
            "From the front-left. Nothing touches the lid's side of the rim. The JP1 shunt is ON (both posts) for the",
            "check on step 14. " + {"TH": "The lead's jacket runs into its own gland, not past the plug.",
                                    "BARO": "Keep the vent and its fin clear of the cable.",
                                    "UV": "The cable rises through the floor and bends over into J1."}[name],
            width=48), warn=True)
        a = Art(c, f"q_bib_{p}_iso", x + 60, y + 20, w - 120, h - 40)
        its = [("JP1 SHUNT ON", "JP1:shunt", "rt"), ("U1 EEPROM", "U1:chip", "lt"), ("J1", "J1:jack", "lt")]
        if name != "TH":
            its.append(("U2 " + {"BARO": "BMP581", "UV": "LTR390"}[name], "U2:sensor", "rt"))
        L(c, a, its, size=8.0)
    return f


def shunt_page(c, pg):
    page(c, "14", "SHUNT ON? METER BEFORE THE LID", "CONTINUITY MODE. EACH BOARD IN ITS BOX, PLUG IN J1, NOTHING AT "
         "THE CABLE'S OTHER END.", pg, SLOGANS_Q[5])
    g = Grid(1, 2, heights=[1.6, 1])
    pod = PD.pod("TH")
    wp, v3 = pod.part("U1").pins["WP"], pod.part("J1").pins["2"]
    x, y, w, h = panel(c, g.cell(0, 0), 1, cap(
        f"The TH board drawn; BARO and UV are the same at these points. Meter probes on U1's WP pin joint ({wp}, the EEPROM",
        f"breakout's pin marked WP) and J1's pin 2 joint ({v3}, 3.3 V: the jack board's second pin from the left, beside",
        "the plug). Shunt ON = BEEP (the EEPROM is write-protected). Silence: the shunt is off or not seated: push it",
        "down over BOTH posts of JP1 (H4, H5) and try again.", width=100))
    a = Art(c, "q_shunt_top", x + 150, y + 4, w - 300, h - 10)
    L(c, a, [(f"PROBE: U1 WP ({wp})", "probe:wp", "lt"), (f"PROBE: J1 PIN 2, 3.3 V ({v3})", "probe:3v3", "lt"),
             ("JP1 SHUNT: ON BOTH POSTS", "JP1:shunt", "rt")])
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["All three before any lid goes on. Tick each. No beep: stop.",
                                            "Photograph it, report to Claude. Do NOT close the box."], warn=True)
    rows = []
    for name in POD:
        pd = PD.pod(name)
        u, j = pd.part("U1").pins["WP"], pd.part("J1").pins["2"]
        rows.append([f"{name} BOX", f"{u} (U1 WP) to {j} (J1 pin 2, 3.3 V)", "BEEP"])
    yy = rows_table(c, x + 16, y + h - 40, w - 30, [("POD", 0), ("PROBE THESE TWO JOINTS", 90), ("MUST", 330)], rows,
                    size=9.5, ticks=True, lead=13)
    para(c, x + 16, yy - 6, wrap_px("The shunt stays ON for good: the station reads the EEPROM, it never writes it. "
                                    "Session P's meter page checked the OFF side (10 kOhm through R1); not again here.",
                                    w - 40, 8.6), 8.6, 11.5, w=w - 30, what="shunt note")


def oring_page(c, pg):
    page(c, "15", "CUT AND SEAT THE O-RING CORD", f"ONE LENGTH PER LID, {CORD:g} MM CORD, BUTT-JOINED. "
         "THE GROOVE IS IN THE LID'S INNER FACE.", pg, SLOGANS_Q[6])
    g = Grid(3, 2, heights=[1.1, 1])
    for k, name in enumerate(POD):
        x, y, w, h = panel(c, g.cell(k, 0), k + 1, [f"{name} LID, inner face up.", f"Cut {FACTS[name]['cut']} mm of cord."])
        a = Art(c, f"q_oring_{name.lower()}", x + 44, y + 8, w - 52, h - 40)
        L(c, a, [("CORD", "cord", "lt")], size=8.0)
    x, y, w, h = panel(c, g.cell(0, 1, 2), 4, cap(
        "1  Cut the cord square with a sharp knife, on the ruler, to the length in the table (the groove's centreline).",
        "2  Press it into the groove all round, starting opposite the join; do not stretch it. 3  The two ends meet in",
        "the middle of the GLAND-END run: a drop of instant glue on one end face, push them together 10 s.", width=66))
    a = Art(c, "q_oring_join", x + 40, y + 24, w - 160, h - 50)
    L(c, a, [("BUTT JOINT", "join", "rt"), ("GROOVE", "groove", "rt")])
    x, y, w, h = panel(c, g.cell(2, 1), 5, ["The cord stands", f"{CORD - FACTS['TH']['depth']:.2f} proud of the face:",
                                            "the lid squeezes it."], warn=True)
    rows = [[n, f"{FACTS[n]['groove']:.1f}", f"{FACTS[n]['cut']}"] for n in POD]
    rows_table(c, x + 10, y + h - 40, w - 16, [("LID", 0), ("GROOVE", 44), ("CUT", 104)], rows, size=9.5, ticks=True,
               lead=13)


def lid_page(c, pg):
    page(c, "16", "LIDS ON: 4 x M3 x 8 EACH", "GROOVE SIDE DOWN ONTO THE RIM. CROSS ORDER. THE LID LANDS FLAT ON "
         "THE RIM: THAT IS THE STOP.", pg, SLOGANS_Q[6])
    g = Grid(3, 2, heights=[1.9, 1])
    for k, name in enumerate(POD):
        cp = {"TH": ["TH: lid on, 4 screws.", "Glands below."], "BARO": ["BARO: lid on, 4 screws.", "Vent below, open."],
              "UV": ["UV: window at the far", "end, over the LTR390."]}[name]
        x, y, w, h = panel(c, g.cell(k, 0), k + 1, cp)
        a = Art(c, f"q_lid_{name.lower()}", x + 10, y + 22, w - 20, h - 44)
        lugs = sorted(n for n in a.anchors if n.startswith("ls:"))
        num = {"BL": "1", "TR": "2", "TL": "3", "BR": "4"}
        L(c, a, [(num[n[3:]], n, "up" if n[3] == "T" else "dn") for n in lugs], size=9)
    x, y, w, h = panel(c, g.cell(0, 1, 3), 4, cap(
        f"1  Check the cord is in its groove all round. 2  Lid onto the rim, groove side down, its 4 holes over the 4 rim",
        f"inserts. 3  {M8} pan head through each hole, by hand first, in the order 1-2-3-4 (opposite corners). 4  Then",
        "snug in the same order until the lid sits flat on the rim all round: STOP there. More torque does not seal better",
        "(the groove sets the squeeze); it strips the insert.", width=100), warn=True)
    rows = [["TH", "after step 14's tick. Then the box goes on the arm (step 18)."],
            ["BARO", "after step 14's tick. The vent stays open below."],
            ["UV", "after step 14's tick AND the window's silicone has cured (step 09)."]]
    rows_table(c, x + 40, y + h - 22, w - 50, [("LID", 0), ("WHEN", 60)], rows, size=9.0, ticks=True, lead=12)


def shield_order(c, pg):
    page(c, "17", "THE SHIELD: PARTS AND FITTING ORDER", "YOUR SHIELD'S PARTS, BOTTOM TO TOP. ONLY THE CAP AND THE "
         "ARM ARE REMIXED. THE ORDER MATTERS.", pg, SLOGANS_Q[7])
    g = Grid(5, 1, heights=[1])
    x, y, w, h = panel(c, g.cell(0, 0, 3), 1, ["Exploded, bottom to top. The cup, stand and plates are",
                                               "your shield's own prints, unchanged."])
    a = Art(c, "q_sh_order", x + 72, y + 6, w - 144, h - 12)
    L(c, a, [("CAP (REMIX)", "cap", "rt"), ("6 PLATES", "plate6", "rt"), ("STAND", "stand", "rt"),
             ("BASE CUP", "cup", "lt"), ("ARM (REMIX)", "arm", "lt"), ("TH BOX", "th", "lt"),
             ("BARO BOX", "baro", "rt")], size=8.0)
    x, y, w, h = panel(c, g.cell(3, 0, 2), 2, ["WHY THIS ORDER: the arm's box", "screws go in from the cup side;",
                                               "the cap's lug screws from inside", "the cap."], warn=True)
    steps = [("18", "TH + BARO BOXES ONTO THE ARM", f"4 x {M10} each, through the face from the CUP side. Cup NOT on yet."),
             ("19", "CUP ONTO THE ARM, STAND, SHT45", "Cup foot on the arm's pocket floor, its 2 holes over the arm's 2. "
              "Stand on the cup. SHT45 tied to the stand."),
             ("--", "6 LOUVER PLATES", "Onto the stand's posts, each on the one below, as your shield goes."),
             ("20", "UV BOX ONTO THE CAP (BENCH)", f"Cap upside down on the bench: 4 x {M10} up into the UV box. Then the "
              "cap onto plate 6, LAST."),
             ("21", "DRIP LOOPS + TIES", "Every cable dips below its gland before it runs to the pole.")]
    yy = y + h - 40
    for n, t, s in steps:
        text(c, x + 12, yy, n, 14, "HEAD", NEON)
        text(c, x + 44, yy, t, 9.6, "HEAD", INK)
        for k, ln in enumerate(wrap_px(s, w - 56, 8.4)):
            text(c, x + 44, yy - 12 - k * 10.5, ln, 8.4, "ALT", INK)
        yy -= 26 + 10.5 * len(wrap_px(s, w - 56, 8.4))
    LAB.block(x + 6, yy + 10, x + w - 4, y + h - 8, "order list")
    para(c, x + 12, yy - 4, wrap_px("The cup's foot holes take the fixings your shield already uses (the 3MF has none "
                                    "drawn). The pole clamp is not drawn either.", w - 24, 8.2), 8.2, 10.5, color=GREY,
         w=w - 20, what="fixings note")


def arm_page(c, pg):
    page(c, "18", "TH AND BARO BOXES ONTO THE ARM", f"4 x {M10} PER BOX, FROM THE CUP SIDE OF EACH FACE INTO THE BOX'S "
         "BACK INSERTS. CUP OFF.", pg, SLOGANS_Q[7])
    g = Grid(2, 2, heights=[1.15, 1])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, cap(
        "The remixed L-arm with both boxes on. TH hangs on the face on the side of the arm's lead hole (its lead comes down",
        "through that hole: step 10); BARO on the opposite face. Each box: back face flat on its face, lid OUTWARD, glands",
        "DOWN. The cup is NOT on the arm yet: the screw heads are where the cup goes.", width=100))
    a = Art(c, "q_arm_iso", x + 140, y + 4, w - 280, h - 10)
    L(c, a, [("TH FACE", "thface", "lt"), ("TH BOX", "thbox", "lt"), ("BARO FACE", "baroface", "rt"),
             ("BARO BOX", "barobox", "rt"), ("UPRIGHT (POLE SIDE)", "upright", "rt")], size=8.0)
    for k, name in enumerate(("TH", "BARO")):
        x, y, w, h = panel(c, g.cell(k, 1), k + 2, [f"{name} face from the cup side: hold the", f"box on the far side; {M10}",
                                                    "through each hole, by hand, then snug."])
        a = Art(c, f"q_arm_{name.lower()}_face", x + 60, y + 6, w - 120, h - 12)
        L(c, a, [(f"{M10}", f"ms{i}", "lt" if i % 2 == 0 else "rt") for i in range(4)], size=8.0)


def sht_page(c, pg):
    page(c, "19", "CUP ON, STAND ON, SHT45 ON THE STAND", "SHT45 ON THE STAND'S INNER FACE: 2 CABLE TIES, PTFE CAP "
         "OUT, LEAD DOWN TO THE CUP.", pg, SLOGANS_Q[7])
    g = Grid(5, 1)
    x, y, w, h = panel(c, g.cell(0, 0, 3), 1, cap(
        "1  Pull the lead's slack down through the cup's hole as the CUP goes", "onto the arm (its foot on the pocket floor). "
        "2  STAND onto the", "cup's disc. 3  SHT45 on the stand's INNER face (the face toward", "the middle), long side "
        "vertical, at mid-height of the plates;", "the lead's jacket beside the strip, down to the cup's hole.", width=48))
    a = Art(c, "q_sht_stand", x + 64, y + 8, w - 128, h - 16)
    L(c, a, [("SHT45", "board", "lt"), ("STRIP", "strip", "lt"), ("LEAD", "lead", "rt"),
             ("CUP HOLE", "cuphole", "rt")], size=8.0)
    x, y, w, h = panel(c, g.cell(3, 0, 2), 2, cap(
        "Close-up: two cable ties round the board and the strip, each over one", "of the board's STEMMA QT sockets (not "
        "over the sensor). Pull snug, cut", "the tails flush. The PTFE cap faces out, into the air; nothing touches it.",
        width=38), warn=True)
    a = Art(c, "q_sht_close", x + 20, y + 24, w - 40, h - 48)
    L(c, a, [("CABLE TIE", "tie0", "up"), ("CABLE TIE", "tie1", "dn"), ("PTFE CAP: CLEAR", "ptfe", "dn")], size=8.0)


def cap_page(c, pg):
    page(c, "20", "UV BOX ONTO THE CAP", f"ON THE BENCH: CAP UPSIDE DOWN, BOX LID DOWN UNDER IT. 4 x {M10} UP INTO "
         "THE BOX. CAP ON LAST.", pg, SLOGANS_Q[7])
    g = Grid(2, 2, heights=[1.1, 1])
    x, y, w, h = panel(c, g.cell(0, 0, 2), 1, cap(
        "On the bench: the UV box lid DOWN on a cloth (protect the window), the cap upside down on it, its saddle over the",
        "box's gland end, the gland in the saddle's notch. 2 screws go down through the cap's flat top into the far-end lug",
        "inserts (down the counterbores inside the cap); 2 through the saddle into the floor-boss inserts.", width=100))
    a = Art(c, "q_cap_bench", x + 130, y + 4, w - 260, h - 8)
    L(c, a, [(f"{M10}: LUG", "lug0", "lt"), (f"{M10}: LUG", "lug1", "lt"), (f"{M10}: SADDLE", "saddle2", "rt"),
             (f"{M10}: SADDLE", "saddle3", "rt")], size=8.0)
    x, y, w, h = panel(c, g.cell(0, 1), 2, ["The cap from below: the 2 lug holes at", "the end of their counterbores, the 2",
                                            "saddle holes in the open."])
    a = Art(c, "q_cap_under", x + 75, y + 20, w - 150, h - 40)
    LH(c, a, [("LUG HOLE", "lug0", "lt"), ("LUG HOLE", "lug1", "lt"), ("SADDLE HOLE", "saddle2", "rt"),
              ("SADDLE HOLE", "saddle3", "rt")], size=8.0)
    x, y, w, h = panel(c, g.cell(1, 1), 3, ["Done, right way up. The gland hangs past", "the saddle; the window faces the "
                                            "sky.", "Now the cap onto plate 6: LAST."], warn=True)
    a = Art(c, "q_cap_iso", x + 20, y + 20, w - 40, h - 40)
    L(c, a, [("UV BOX", "uvbox", "up"), ("WINDOW", "window", "up"), ("FLOOR GLAND", "gland", "dn")], size=8.0)


def drip_page(c, pg):
    page(c, "21", "DRIP LOOPS", "EVERY CABLE DIPS BELOW ITS GLAND, THEN RUNS TO THE POLE. "
         "WATER DRIPS OFF THE LOW POINT.", pg, SLOGANS_Q[7])
    g = Grid(5, 1, heights=[1])
    x, y, w, h = panel(c, g.cell(0, 0, 3), 1, ["The finished stack, all four cables. The routes are",
                                               "illustrative: keep the dips, not the exact path."])
    a = Art(c, "q_drip", x + 62, y + 6, w - 124, h - 12)
    L(c, a, [("UV CABLE", "gland:UV", "lt"), ("UV LOOP", "low:uv_cable", "lt"), ("TH LOOP", "low:th_cable", "lt"),
             ("TH LEAD", "low:th_lead", "rt"), ("BARO LOOP", "low:baro_cable", "rt")], size=8.0)
    x, y, w, h = panel(c, g.cell(3, 0, 2), 2, ["Tick each cable when its loop", "is set and tied. Then each dome",
                                               "nut once more by hand: snug,", "not crushed."], warn=True)
    rows = [["TH PORT CABLE", "straight down from the TH box's gland, a dip below it, then back up to the pole."],
            ["TH SHT45 LEAD", "comes UP into its gland from below: the low point is under the TH face (step 10)."],
            ["BARO PORT CABLE", "straight down from the BARO box's gland, a dip below it, then to the pole."],
            ["UV PORT CABLE", "down the outside of the louvers on the BARO side, a dip at the bottom, then to the pole."]]
    yy = rows_table(c, x + 12, y + h - 40, w - 20, [("CABLE", 0), ("ITS LOOP", 74)], rows, size=8.4, ticks=True, lead=11)
    para(c, x + 12, yy - 6, wrap_px("Tie each cable to the arm's upright or the pole above its loop, never IN the loop. "
                                    "Nothing pulls on a gland. The dips sit lower than every gland.", w - 24, 8.6), 8.6,
         11.5, w=w - 20, what="tie note")


# ------------------------------------------------------------------ the page list
def build_pages():
    PAGES.clear()
    add_page("00", "SESSION Q: BOXES, SHIELD, INSTALL",
             ["parts-as-supplied", "parts:box", "parts:insert", "parts:gland", "parts:oring", "parts:lid-screw",
              "parts:mount-screw", "parts:board-screw", "parts:uv-window", "parts:cap", "parts:arm", "parts:cable-tie"], cover)
    add_page("00", "BEFORE YOU START", ["tools", "steps"], before)
    add_page("01", "KNOW THE THREE BOXES", ["box-faces"], faces)
    for k, name in enumerate(POD):
        st = f"{k + 2:02d}"
        add_page(st, f"{name} BOX: HEAT-SET INSERTS", [f"{name}:inserts"], inserts_page(name, st))
    add_page("05", "THE PG-7 #762 AS SUPPLIED", ["gland", "gland:as-supplied", "gland:locknut-off"], gland_supplied)
    for k, name in enumerate(POD):
        st = f"{k + 6:02d}"
        extra = {"TH": ["TH:lead-gland"], "BARO": ["BARO:vent"], "UV": []}[name]
        add_page(st, {"TH": "TH BOX: TWO GLANDS", "BARO": "BARO BOX: GLAND + VENT", "UV": "UV BOX: THE FLOOR GLAND"}[name],
                 ["gland", f"{name}:gland"] + extra, gland_page(name, st))
    add_page("09", "UV LID: THE WINDOW", ["UV:window"], window_page)
    add_page("10", "TH: THE SHT45 LEAD, CUP + ARM + GLAND", ["lead-through-cup", "TH:lead-route"], lead_page)
    for k, name in enumerate(POD):
        st = f"{k + 11:02d}"
        add_page(st, f"{name} BOARD INTO THE {name} BOX", [f"{name}:board-in-box"], bib_page(name, st))
    add_page("14", "SHUNT ON? METER BEFORE THE LID", ["shunt-check"] + [f"{n}:shunt" for n in POD], shunt_page)
    add_page("15", "CUT AND SEAT THE O-RING CORD", ["oring", "oring:cut"], oring_page)
    add_page("16", "LIDS ON: 4 x M3 x 8 EACH", ["lid", "lid:screws"] + [f"{n}:lid" for n in POD], lid_page)
    add_page("17", "THE SHIELD: PARTS AND FITTING ORDER", ["shield-order"], shield_order)
    add_page("18", "TH AND BARO BOXES ONTO THE ARM", ["arm-mount", "TH:arm", "BARO:arm"], arm_page)
    add_page("19", "CUP ON, STAND ON, SHT45 ON THE STAND", ["sht45-stand"], sht_page)
    add_page("20", "UV BOX ONTO THE CAP", ["uv-cap", "UV:cap"], cap_page)
    add_page("21", "DRIP LOOPS", ["drip-loops"] + [f"{n}:drip-loop" for n in POD], drip_page)


build_pages()
STEP_LIST = []
for _st, _t, _tags, _fn in PAGES:
    if _st != "00" and (not STEP_LIST or STEP_LIST[-1][0] != _st):
        STEP_LIST.append((_st, _t))


def build(path, report=True):
    cv = canvas.Canvas(str(path), pagesize=(W, H))
    cv.setTitle("Session Q: the pod boxes, the shield and the install")
    cv.setAuthor("PODS-R1")
    labels, holes, man = 0, [], []
    for i, (st, title, tags, fn) in enumerate(PAGES):
        pg = i + 1
        fn(cv, pg)
        iss = LAB.check() if report else []
        hi = SL.HC.check(pg) if report else []
        for m in hi:
            print("  HOLE", m)
        labels += len(iss)
        holes += hi
        SL.HC.reset()
        cv.showPage()
        man.append({"page": pg, "step": st, "title": title, "tags": tags, "label_issues": len(iss), "hole_issues": len(hi)})
    cv.save()
    return labels, holes, man


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "session-q-install.pdf"
    bad, hole_issues, man = build(dest)
    stats = dict(SL.HC.STATS)
    json.dump({"pdf": dest.name, "page_count": len(man), "label_issues": bad, "hole_issues": len(hole_issues),
               "hole_stats": stats, "pages": man}, open(OUT / "session-q-manifest.json", "w"), indent=1)
    print("ok", len(man), "pages,", bad, "label issues,", len(hole_issues), "hole-alignment issues", stats)
    if hole_issues or bad:
        sys.exit("BUILD FAILED: label or hole-callout issues")
