"""Read hardware/tx-stack-r1/build/ASSEMBLY.md (written by layout/drawings.py) for the Session 7 and 8 sheets.

Exposes: CHARGER (section 1, the seven numbered steps), PRINTS / BOX (section 2, its numbered steps), CARDS (section
3 text), LEADS (section 4 table rows: from, to, length, what), BEFORE (section 5 bullets), plus a few facts pulled out
of the text with asserts, so a reworded doc fails loudly instead of drifting from the pages.
"""
import re
from pathlib import Path

DOC = Path(__file__).resolve().parents[2] / "build" / "ASSEMBLY.md"
TXT = DOC.read_text()


def section(n):
    m = re.search(rf"^## {n}\. .*?$(.*?)(?=^## |\Z)", TXT, re.S | re.M)
    assert m, f"ASSEMBLY.md has no section {n}"
    return m.group(1)


def steps(body):
    """Numbered list items (top level), their continuation lines joined."""
    out, cur = [], None
    for ln in body.splitlines():
        m = re.match(r"^(\d+)\. (.*)", ln)
        if m:
            cur = [int(m.group(1)), m.group(2)]
            out.append(cur)
        elif cur and ln.startswith("   ") and ln.strip():
            cur[1] += "\n" + ln.strip()
    return [(n, t) for n, t in out]


def plain(s):
    return re.sub(r"\*\*(.*?)\*\*", r"\1", s).replace("`", "")


CHARGER = steps(section(1))
assert [n for n, _ in CHARGER] == list(range(1, 8)), CHARGER
BOX = steps(section(2))
assert [n for n, _ in BOX] == list(range(1, 9)), [n for n, _ in BOX]
CARDS = section(3)
LEADS = []
for ln in section(4).splitlines():
    if ln.startswith("| ") and not ln.startswith("| From") and not ln.startswith("|---"):
        LEADS.append(tuple(c.strip() for c in ln.strip("|").split("|")))
BEFORE = [ln[2:].strip() for ln in section(5).splitlines() if ln.startswith("- ")]

# facts the pages print, pulled from the text
C = {n: plain(t) for n, t in CHARGER}
assert "JP24 off, JP22 on" in C[1] and "JP9 off" in C[2] and "SNS_BATP" in C[2] and "JP18 off" in C[3]
assert "#372" in C[3] and "J7" in C[3] and "JP12, JP17 and JP30 stay in" in C[4] and "JP32" in C[5]
assert "J6, micro-B" in C[6] and "JP17 out" in C[7] and "REG0x0A" in C[7] and "0.9 A" in C[7]
ICHG = re.search(r"about ([\d.]+) A", C[7]).group(1)
LEAD = {r[0]: r for r in LEADS}
for k in ("PG1 lead -", "RT1 1", "RT1 2", "PG1 lead +", "U1 battery + (J5 BATTERY)", "U1 system out (J3 SYS)",
          "U1 system ground (J3 GND)", "R7 2", "EVM J8 (KK 4-pin housing, pins 1-3)"):
    assert k in LEAD, (k, list(LEAD))
B = {n: plain(t) for n, t in BOX}
assert "PG-7s #762" in B[4] and "PG-9s #761" in B[4] and "M12 vent" in B[4] and "SMA bulkhead" in B[4]
assert "2 3.3 V, 3 data, 4 ground, 5 clock" in B[6] and "wind 2-5, rain 3-4" in B[6]
assert "135110" in B[7] and "four printed bolts" in B[8]
PORT_PINS = [("2", "3.3 V"), ("3", "data (SDA)"), ("4", "ground"), ("5", "clock (SCL)")]
LOOP = re.search(r"leave (\d+-\d+) mm service loops", section(4)).group(1)
