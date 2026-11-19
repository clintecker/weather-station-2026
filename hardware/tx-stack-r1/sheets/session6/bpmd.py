"""Reader for build/BACKPLANE.md (layout/drawings.py writes it): the facts Session 6's pages print.

Every table the sheet uses is parsed here; scenes6.py cross-checks them against layout/stack.py on import, so the
page text and the pictures cannot drift apart quietly."""
import re
from pathlib import Path

MD = Path("/Users/clint/code/electronics/weather-station-2026/hardware/tx-stack-r1/build/BACKPLANE.md").read_text()


def section(title_start):
    """Body of the '## ...' section whose title starts with title_start (up to the next '## ')."""
    m = re.search(r"^## " + re.escape(title_start) + r".*?$\n(.*?)(?=^## |\Z)", MD, re.M | re.S)
    assert m, f"BACKPLANE.md: no section {title_start!r}"
    return m.group(1)


def table(body, after=None):
    """The first markdown table in body (after the line containing `after`): list of row lists."""
    if after:
        body = body[body.index(after):]
    rows = []
    started = False
    for ln in body.splitlines():
        if ln.startswith("|"):
            started = True
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            rows.append(cells)
        elif started:
            break
    return rows[1:]                                   # drop the header row


S2 = section("2. Sockets")
SOCKETS = {}                                          # XB4 -> dict(card, hole, key, colour)
for sock, card, hole, key, colour in table(S2):
    ref = sock.split()[0]
    b = re.search(r"socket for (B\d)", card).group(1)
    k = int(re.match(r"contact (\d+): line \1, hole (\d+)", key).group(1))
    SOCKETS[ref] = dict(card=b, hole=int(hole), key=k, colour=colour)
ISOLATED = {}                                         # XB4 -> [lines]
for ref, hole, spans in re.findall(r"^- (XB\d) \(hole (\d+)\) lines (.+)$", S2, re.M):
    lines = []
    for part in spans.split(", "):
        a, _, b = part.partition("-")
        lines += list(range(int(a), int(b or a) + 1))
    ISOLATED[ref] = lines
assert set(ISOLATED) == set(SOCKETS), ISOLATED

S3 = section("3. Pins and parts on the front")
FRONT = []                                            # (ref, note, pin, line, hole, net)
for part, pin, lh, net in table(S3):
    ref, note = re.match(r"(\w+) \((.*)\)$", part).groups()
    ln, hl = (int(v) for v in lh.split(", "))
    FRONT.append((ref, note, pin, ln, hl, net))
EVM = []                                              # (from, line, hole, what): backplane end of each lead
for frm, to, what in table(S3, "### Leads to the charger and the pack"):
    m = re.match(r"line (\d+), hole (\d+)", to) or re.search(r"\(line (\d+), hole (\d+)\)", to)
    EVM.append((frm, int(m.group(1)), int(m.group(2)), what, to))
assert len(EVM) == 5, EVM

S4 = section("4. Bus wires")
STOCK = re.search(r"Use (bare 22 AWG solid copper: the Adafruit 1311 hook-up wire on hand), stripped \(([\d.]+) mm\)", S4)
assert STOCK, "BACKPLANE.md section 4: the bus wire stock sentence changed"
BUS_STOCK, BUS_D = STOCK.group(1), float(STOCK.group(2))
BUS = []                                              # (line, net, first, last, cut_mm, [holes])
for ln, net, a, b, cut, holes in table(S4):
    if a == "-":
        continue
    BUS.append((int(ln), net, int(a), int(b), int(cut.split()[0]), [int(v) for v in holes.split(", ")]))

S5 = section("5. Leads on the copper side")
LEADS = []                                            # (from, to, length, net, what)
for frm, to, length, net, what in table(S5):
    LEADS.append((frm, to, length, net, what))
MUX_PARA = re.search(r"^The mux is an Adafruit #5626\..*$", S5, re.M).group(0)
assert "Bridge A0 for address 0x71" in MUX_PARA and "SW1 to V+" in MUX_PARA, MUX_PARA
MUX_LEADS = []                                        # (pad, line, hole, cut mm): header pins, then CHk.SDA/SCL
for frm, to, length, net, what in LEADS:
    m = re.match(r"U4 (\w+)$", frm) or re.match(r"U4 (CH[0-3]) (SDA|SCL)$", frm)
    if m:
        t = re.match(r"backplane line (\d+) hole (\d+)", to)
        pad = m.group(1) if m.lastindex == 1 else f"{m.group(1)}.{m.group(2)}"
        assert pad.startswith("CH") == length.endswith("of cable"), (frm, length)
        MUX_LEADS.append((pad, int(t.group(1)), int(t.group(2)), int(length.split()[0])))
assert len(MUX_LEADS) == 13, MUX_LEADS
JUMPERS = []                                          # ((line, hole), (line, hole), what, cut mm)
for frm, to, length, net, what in LEADS:
    a = re.match(r"backplane line (\d+) hole (\d+)$", frm)
    b = re.match(r"backplane line (\d+) hole (\d+)$", to)
    if a and b:
        JUMPERS.append(((int(a.group(1)), int(a.group(2))), (int(b.group(1)), int(b.group(2))), what, int(length.split()[0])))
assert len(JUMPERS) == 3, JUMPERS

BEFORE = [ln[2:] for ln in section("Before power").splitlines() if ln.startswith("- ")]
assert len(BEFORE) == 5, BEFORE
MUX_PADS_PARA = re.search(r"^VIN, GND, SCL, SDA and RST are 22 AWG.*$", S5, re.M).group(0)
assert "#4209" in MUX_PARA and "red (V+)" in MUX_PADS_PARA, MUX_PADS_PARA
EVM_LEN = {frm: length for frm, to, length, net, what in LEADS if frm.startswith(("PG1 lead +", "U1 ")) or frm == "R7 2"}
