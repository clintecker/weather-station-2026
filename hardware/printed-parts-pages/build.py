"""Build one page per printed part, plus the index, from hardware/PRINTED-PARTS.md, the committed STLs and the CAD.
Run with the CAD venv:  .venv-cad/bin/python -B build.py OUTDIR [--urls urls.json] [--index-only]   (publish.sh does this)
Writes OUTDIR/<slug>/ for every part page, OUTDIR/printed-parts/ (the index) and OUTDIR/pages.json (each slug and the
visibility publish.sh gives it). meshes.py (run as a subprocess) builds what isn't a committed STL into OUTDIR/_meshes/.
--urls: the {slug: url} map the host returned when the part pages went up; the index links to those.

Two kinds of page:
- Our own CAD (the TX parts, the pod boxes, the test prints): published to `everyone`.
- Anything derived from the radiation shield's 3MF (unknown licence): see RESTRICTED below. Those pages are published
  restricted to Clint's login only, and nothing they hold is committed. The public pages and the index never show a
  shield mesh, render or number: the shield's sections are skipped there, and the attachment rows that touch the
  remixed cap and arm are rewritten to show only our side.
"""
import html
import json
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
HW = HERE.parent
DOC = (HW / "PRINTED-PARTS.md").read_text()
HOST = "https://artifacts.folk-fujita.ts.net/p/"
INDEX = "printed-parts"

TX_STL = HW / "tx-stack-r1/cage/stl"
POD_STL = HW / "pods-r1/box/stl"
BODY_C, LID_C = "#e4ddcf", "#b9c8d0"          # light PETG, the lid a touch cooler so the two read apart
UV_AXIS = (10.16, 13.375)                       # the crown's axis in the board frame (PRINTED-PARTS.md, UV crown body)
POD_LID_AT = 18.14 + 9.5                        # TH/BARO: rim z 18.14 less the back face z -9.5
UV_LID_AT = 20.84 + 9.5                         # UV: the ledge z 20.84 less the floor z -9.5
NOT_SHOWN = "the remixed shield {} (restricted page)"

READY = ("ok", "ready to print")
POD_SHARED = ["Walls", "Inside corner", "Clearance", "Gland nut", "Gland hole", "M3 heat-set", "Board standoffs",
              "Board screws", "O-ring"]

PARTS = [
    dict(slug="printed-evm-clips", short="clips", title="EVM front clips", sub="tx-stack-r1 · cage.py", badge=READY,
         summary="EVM front clips", sections=["### EVM front clips"], base=["Clip inserts", "EVM supports"],
         rows=[4, 5], stl=[(TX_STL / "evm-clips.stl", "clips", "#d9d4c7")],
         desc="Two small L-clips that hold the BQ25798EVM's front edge down in the TX box. 3D view, numbers and STL."),
    dict(slug="printed-lid-shade", short="shade", title="Lid shade", sub="tx-stack-r1 · cage.py",
         badge=("ok", "ready to print · the first print is its fit test"), summary="Lid shade",
         sections=["### Lid shade"], base=["Lid-bolt bores"], rows=[3],
         stl=[(TX_STL / "lid-shade.stl", "shade", "#f2f2ef")],
         view_note="Shown as it lies on the bed: plate down, skirt and feet up.",
         desc="The white PETG cover that keeps sun off the TX box's clear lid. 3D view, numbers and STL."),
    dict(slug="printed-pod-th", short="TH pod", title="TH pod body and lid", sub="pods-r1 · podbox.py", badge=READY,
         summary=["TH pod body", "TH pod lid"], pod="TH", sections=["### TH pod body and lid"],
         rows=[11, 14, 15, 16, 17],
         stl=[(POD_STL / "pod-th-body.stl", "body", BODY_C), (POD_STL / "pod-th-lid.stl", "lid", LID_C, POD_LID_AT, 45)],
         desc="The sealed box for the TH pod board, body and screw-on lid. 3D view, numbers and both STLs."),
    dict(slug="printed-pod-baro", short="BARO pod", title="BARO pod body and lid", sub="pods-r1 · podbox.py", badge=READY,
         summary=["BARO pod body", "BARO pod lid"], pod="BARO", sections=["### BARO pod body and lid"],
         rows=[11, 14, 15, 16, 17, 22],
         stl=[(POD_STL / "pod-baro-body.stl", "body", BODY_C), (POD_STL / "pod-baro-lid.stl", "lid", LID_C, POD_LID_AT, 45)],
         desc="The vented box for the BARO pod board, body and screw-on lid. 3D view, numbers and both STLs."),
    dict(slug="printed-uv-crown-body", short="UV body", title="UV crown body", sub="pods-r1 · podbox.py", badge=READY,
         summary="UV crown body", pod="UV", sections=["### UV crown body"], rows=[11, 16, 18, 19, 22, 23],
         stl=[(POD_STL / "pod-uv-body.stl", "body", BODY_C),
              (POD_STL / "pod-uv-lid.stl", "lid", LID_C, UV_LID_AT, 55, 25, "context")],
         desc="The drum of the UV pod: bayonet spigot, radial O-ring groove, port gland and floor bosses. 3D view and STL."),
    dict(slug="printed-uv-crown-lid", short="UV lid", title="UV crown lid (dome)", sub="pods-r1 · podbox.py",
         badge=("wait", "waiting on uv_window: measure the JGS1 disc first"),
         summary="UV crown lid (dome)", pod="UV", sections=["### UV crown lid"], rows=[18, 19, 20, 21],
         stl=[(POD_STL / "pod-uv-body.stl", "body", BODY_C, 0, 0, 0, "context"),
              (POD_STL / "pod-uv-lid.stl", "lid", LID_C, UV_LID_AT, 55, 25)],
         desc="The UV pod's dome lid: bayonet skirt, window recess and LTR390 bosses. 3D view and STL."),
    dict(slug="printed-retention-bar", short="bar", title="Retention bar", sub="tx-stack-r1 · cage.py",
         badge=("no", "not ready to print: no export yet, screw length unset"),
         summary="Retention bar", sections=["### Retention bar"], base=["Retention bar inserts", "Card slots"],
         rows=[6, 7], stl="bar",
         view_note="A preview only: built here from cage.py's bar_solid() through true_frame(), laid flat. No STL of it "
                   "is committed, and cage.py has no print pose or exporter for it yet.",
         desc="The flat strip that stops the TX cards backing out. Not ready to print yet. Preview 3D view and numbers."),
    dict(slug="printed-rim-ring", short="rim ring", title="Rim test ring", sub="tx-stack-r1 · cage.py", badge=("test", "test print"),
         summary="Rim test ring", sections=["### Rim test ring"], base=["Wall top and lip", "Lid-bolt bores"],
         rows=[1, 2], rows_note="It isn't in the attachment table itself. It tests these two base joints.",
         stl=[(TX_STL / "rim-ring.stl", "ring", "#d9d4c7")],
         desc="A test print of the TX base's sealing lip and bolt holes, checked on the real lid. 3D view and STL."),
    dict(slug="printed-base-coupon", short="coupon", title="Base test coupon", sub="tx-stack-r1 · cage.py", badge=("test", "test print"),
         summary="Base test coupon", sections=["### Base test coupon"],
         base=["Card slots", "Lid-bolt bores", "Wall top and lip"], rows=[1, 7],
         rows_note="It isn't in the attachment table itself. It tries these two base joints.",
         stl=[(TX_STL / "coupon.stl", "coupon", "#d9d4c7")],
         desc="A test print of the TX base's top-left corner: card slot, lid-bolt bore, lip and a leak patch. 3D view and STL."),
]

# attachment rows that touch the remixed cap and arm: only our side, never a number from remix.py
ROW_OVERRIDE = {
    17: ["17", "TH / BARO box → " + NOT_SHOWN.format("arm"),
         "4 x M3 x 10 pan head A2 per box into the box's back-face lug inserts",
         NOT_SHOWN.format("arm"), "back-face lug inserts, Ø4.0 x 6.7 blind", "`pod_mount_screw`"],
    23: ["23", "UV crown → " + NOT_SHOWN.format("cap"), "4 x M3 x 10 pan head A2 up into the crown's floor-boss inserts",
         NOT_SHOWN.format("cap"), "floor-boss inserts on r 31", "`pod_mount_screw`"],
    24: ["24", NOT_SHOWN.format("arm") + " → pole", "hose clamp", NOT_SHOWN.format("arm"), "pole", "-"],
}
TEXT_FIX = [("stands on the remixed shield cap", "stands on " + NOT_SHOWN.format("cap"))]

# ---------------------------------------------------------------- markdown


def lines_of(doc):
    return doc.splitlines()


def section(heading, until_level=None):
    """The lines under the first heading that starts with `heading`, up to the next heading of the same or a higher
    level (or, with until_level, the next heading of that level or higher)."""
    L = lines_of(DOC)
    lvl = len(heading.split(" ")[0])
    for i, ln in enumerate(L):
        if ln.startswith(heading):
            stop = until_level or lvl
            out = []
            for ln2 in L[i + 1:]:
                m = re.match(r"^(#+) ", ln2)
                if m and len(m.group(1)) <= stop:
                    break
                out.append(ln2)
            while out and out[-1].strip() in ("", "---"):
                out.pop()
            return out
    raise SystemExit(f"PRINTED-PARTS.md has no heading {heading!r}")


def inline(s):
    for a, b in TEXT_FIX:
        s = s.replace(a, b)
    s = re.sub(r"\[([^\]]+)\]\(#[^)]*\)", r"\1", s)              # in-doc anchors: keep the words
    parts = re.split(r"(`[^`]*`)", s)
    out = []
    for p in parts:
        if p.startswith("`") and p.endswith("`") and len(p) > 1:
            out.append("<code>" + html.escape(p[1:-1]) + "</code>")
        else:
            p = html.escape(p, quote=False)
            p = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p)
            out.append(p)
    return "".join(out)


def cells(row):
    return [c.strip() for c in row.strip().strip("|").split("|")]


def table_html(rows, linker=None):
    head, body = cells(rows[0]), [cells(r) for r in rows[2:]]
    h = ['<div class="tbl"><table>']
    keyed = not any(head)
    if not keyed:
        h.append("<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead>")
    h.append("<tbody>")
    for r in body:
        tds = []
        for k, c in enumerate(r):
            txt = linker(k, c) if linker else inline(c)
            tag = "th" if k == 0 and (keyed or not head[0]) else "td"
            tds.append(f'<{tag}{" scope=row" if tag == "th" else ""}>{txt}</{tag}>')
        h.append("<tr>" + "".join(tds) + "</tr>")
    h.append("</tbody></table></div>")
    return "".join(h)


LABEL = re.compile(r"^(Mates with|Checks|Open items|Purpose|What it's waiting for|Run|Regenerate[^:]*)(:)")


def md_html(lines, hshift=0):
    """A small renderer for the bits PRINTED-PARTS.md uses: headings, tables, lists (one level of nesting), code
    fences and paragraphs."""
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip() or ln.strip() == "---":
            i += 1
            continue
        m = re.match(r"^(#+) (.*)", ln)
        if m:
            lvl = min(6, len(m.group(1)) + hshift)
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
            continue
        if ln.startswith("```"):
            j = i + 1
            while not lines[j].startswith("```"):
                j += 1
            out.append("<pre><code>" + html.escape("\n".join(lines[i + 1:j])) + "</code></pre>")
            i = j + 1
            continue
        if ln.startswith("|"):
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            out.append(table_html(lines[i:j]))
            i = j
            continue
        if re.match(r"^(\s*)(- |\d+\. )", ln):
            ordered = bool(re.match(r"^\s*\d+\. ", ln))
            items = []                                     # (depth, text)
            while i < len(lines) and lines[i].strip() and not lines[i].startswith("|"):
                m = re.match(r"^(\s*)(- |\d+\. )(.*)", lines[i])
                if m:
                    items.append([len(m.group(1)) // 2, m.group(3)])
                else:
                    items[-1][1] += " " + lines[i].strip()
                i += 1
            tag = "ol" if ordered else "ul"
            h, depth = [f"<{tag}>"], 0
            for k, (d, t) in enumerate(items):
                if d > depth:
                    h.append("<ul>")
                elif d < depth:
                    h.append("</li></ul></li>")
                elif k:
                    h.append("</li>")
                depth = d
                h.append("<li>" + inline(t))
            h.append("</li>" + ("</ul></li>" if depth else "") + f"</{tag}>")
            out.append("".join(h))
            continue
        j = i
        para = []
        while j < len(lines) and lines[j].strip() and not re.match(r"^(#+ |\||```|\s*- |\d+\. )", lines[j]):
            para.append(lines[j].strip())
            j += 1
        txt = inline(" ".join(para))
        txt = LABEL.sub(r"<strong>\1</strong>\2", txt)
        out.append(f"<p>{txt}</p>")
        i = j
    return "\n".join(out)


def table_rows(heading, until_level=None):
    """The rows of the first table under a heading, as cell lists (header first)."""
    L = section(heading, until_level)
    t = [ln for ln in L if ln.startswith("|")]
    return t


def first_table(lines):
    out, started = [], False
    for ln in lines:
        if ln.startswith("|"):
            out.append(ln)
            started = True
        elif started:
            break
    return out


def pick_rows(table, keep):
    """Header, rule, then only the rows whose first cell starts with one of `keep` (in table order)."""
    return table[:2] + [r for r in table[2:] if any(cells(r)[0].startswith(k) for k in keep)]


def to_md_row(c):
    return "| " + " | ".join(c) + " |"


ATTACH = first_table(section("## Attachment points"))
ATTACH_HEAD = ATTACH[:2]
ATTACH_ROWS, ATTACH_ORIG = {}, {}
for r in ATTACH[2:]:
    c = cells(r)
    n = int(c[0])
    ATTACH_ORIG[n] = r
    ATTACH_ROWS[n] = to_md_row(ROW_OVERRIDE[n]) if n in ROW_OVERRIDE else r

SUMMARY = first_table(section("## Summary"))
SUMMARY_ROWS = {cells(r)[0]: cells(r) for r in SUMMARY[2:]}


def summary_row(name):
    hits = [c for k, c in SUMMARY_ROWS.items() if k.startswith(name)]
    assert len(hits) == 1, name
    return hits[0]


BASE_IF = first_table(section("### Interfaces on the base"))

# ---------------------------------------------------------------- pages

TEMPLATE = (HERE / "template.html").read_text()
SCRIPTS = ('<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>\n'
           '<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>\n'
           '<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/STLLoader.js"></script>\n'
           '<script src="viewer.js"></script>')


def page(title, desc, main, scripts=""):
    return (TEMPLATE.replace("%%TITLE%%", html.escape(title)).replace("%%DESC%%", html.escape(desc))
            .replace("%%MAIN%%", main).replace("%%SCRIPTS%%", scripts))


def badge(b):
    return f'<span class="badge b-{b[0]}">{html.escape(b[1])}</span>'


def export_bar(dst):
    """The retention bar from cage.py (box solid + bar_solid holes, through true_frame), laid flat on the origin.
    Written into the page folder only: no STL of it is committed."""
    sys.path.insert(0, str(HW / "tx-stack-r1/cage"))
    import cadquery as cq
    import cage
    p = next(p for p in cage.parts() if p.name == "retention bar")
    assert len(p.boxes) == 1 and not p.cuts
    b = p.boxes[0]
    s = cq.Workplane("XY").box(b.x1 - b.x0, b.y1 - b.y0, b.z1 - b.z0, centered=False).translate((b.x0, b.y0, b.z0))
    s = cage.true_frame(p.solid(s))
    bb = s.val().BoundingBox()
    s = s.translate((-bb.xmin, -bb.ymin, -bb.zmin))
    cq.exporters.export(s, str(dst), tolerance=0.02, angularTolerance=0.1)
    return s.val().Volume() / 1000


def viewer_html(p, meshes):
    two = len(meshes) > 1
    rail = []
    if two:
        rail.append('<label for="explode">take apart <input type="range" id="explode" min="0" max="1" step="0.01" '
                    'value="0.45"> <output id="explode-v"></output></label>')
        for m in meshes:
            label = "show the " + m["name"] + (" (its own page)" if m.get("context") else "")
            rail.append(f'<label><input type="checkbox" data-show="{m["name"]}" checked> {html.escape(label)}</label>')
    rail.append('<label for="cut"><input type="checkbox" id="cut"> cut</label>'
                '<label for="cut-at">at <input type="range" id="cut-at" min="0.02" max="0.98" step="0.01" value="0.5">'
                ' <output id="cut-v"></output></label>'
                '<label for="cut-axis">across <select id="cut-axis"><option value="x">x</option>'
                '<option value="y">y</option></select></label>')
    rail.append('<button type="button" id="spin">stop turning</button><button type="button" id="reset">reset view</button>')
    hint = "Drag to turn, pinch or scroll to zoom, right-drag to pan."
    if two:
        hint += " Slide &lsquo;take apart&rsquo; to lift the lid off" + (" (it turns back 25&deg; to unlock first)."
                                                                          if p.get("pod") == "UV" else ".")
    if p.get("view_note"):
        hint += " " + html.escape(p["view_note"])
    return ('<figure class="stage">'
            f'<div id="view" role="img" aria-label="3D model of the {html.escape(p["title"])}; drag to turn"></div>'
            '<div id="status">loading the model…</div>'
            f'<div class="rail">{"".join(rail)}</div><div class="hint">{hint}</div></figure>')


def summary_facts(p, files):
    names = p["summary"] if isinstance(p["summary"], list) else [p["summary"]]
    rows = [summary_row(n) for n in names]
    f = []
    f.append(("Material", rows[0][3]))
    env = "; ".join((r[0].split()[-1] + " " if len(rows) > 1 else "") + r[4] for r in rows)
    f.append(("Envelope (mm, as the STL lies)", env))
    f.append(("Quantity", rows[0][5]))
    f.append(("Status in the doc", " / ".join(r[1] for r in rows)))
    facts = "".join(f'<div class="fact"><b>{html.escape(k)}</b><span>{inline(v)}</span></div>' for k, v in f)
    dls = "".join(f'<a class="dl" href="{n}" download>Download {n}</a>' for n in files)
    return f'<section class="facts" aria-label="Key facts">{facts}</section><div style="display:flex;flex-wrap:wrap;gap:10px">{dls}</div>'


def pod_checks(col):
    lines = section("### Pod checks and their last numbers")
    intro = [ln for ln in lines if not ln.startswith("|")]
    t = first_table(lines)
    head = cells(t[0])
    k = head.index(col)
    rows = [to_md_row([cells(r)[0], cells(r)[1], cells(r)[k]]) for r in t[2:] if cells(r)[k] not in ("-", "")]
    tbl = [to_md_row([head[0], head[1], col]), "|---|---|---|"] + rows
    return md_html(intro) + "\n" + table_html(tbl)


def part_page(p, out):
    d = out / p["slug"]
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    meshes, files = [], []
    if p["stl"] == "bar":
        vol = export_bar(d / "retention-bar.stl")
        print(f"  retention bar exported: {vol:.2f} cm3")
        meshes.append(dict(file="retention-bar.stl", name="bar", color="#d9d4c7", at=[0, 0, 0]))
        files.append("retention-bar.stl")
    else:
        for e in p["stl"]:
            src, name, color = e[:3]
            at = e[3] if len(e) > 3 else 0
            lift = e[4] if len(e) > 4 else 0
            turn = e[5] if len(e) > 5 else 0
            context = len(e) > 6 and e[6] == "context"
            shutil.copy2(src, d / src.name)
            m = dict(file=src.name, name=name, color=color, at=[0, 0, at], lift=lift, turn=turn)
            if turn:
                m["axis"] = list(UV_AXIS)
            if context:
                m["context"] = True
            else:
                files.append(src.name)
            meshes.append(m)
    (d / "part.json").write_text(json.dumps(dict(meshes=meshes)))
    shutil.copy2(HERE / "viewer.js", d / "viewer.js")

    body = []
    back = HOST + INDEX + "/"
    body.append(f'<header><a class="back" href="{back}" target="_top">&larr; all printed parts</a>'
                f'<div class="eyebrow">printed part · {html.escape(p["sub"])}</div>'
                f'<h1>{html.escape(p["title"])}</h1>{badge(p["badge"])}'
                f'<p class="lede">{html.escape(p["desc"].split(". ")[0])}.</p></header>')
    body.append(viewer_html(p, meshes))
    if any(m.get("context") for m in meshes):
        other = [m for m in meshes if m.get("context")][0]["name"]
        body.append(f'<p class="note">The {other} is drawn so you can see how the two fit. It has its own page and STL.</p>')
    body.append(summary_facts(p, files))
    if p.get("pod"):
        intro = section("## Pod boxes", until_level=3)
        body.append('<section><h2>All pod boxes: regenerate, print rules, shared numbers</h2>' + md_html(intro) + "</section>")
    for h in p["sections"]:
        body.append(f"<section><h2>From PRINTED-PARTS.md</h2>{md_html(section(h), hshift=1)}</section>")
    if p.get("base"):
        body.append('<section><h2>What it meets on the TX base</h2><p class="lede">From the base\'s interface table '
                    '(the base is settled; box frame, mm).</p>' + table_html(pick_rows(BASE_IF, p["base"])) + "</section>")
    if p.get("pod"):
        body.append(f'<section><h2>Checks and their last numbers ({p["pod"]})</h2>{pod_checks(p["pod"])}</section>')
        body.append('<section><h2>Open items for every pod box</h2>'
                    + md_html(section("### Pod open items"))
                    + '<p class="lede">These are shared by all three pod boxes. Each one regenerates the boxes when it changes.</p></section>')
    rows = ATTACH_HEAD + [ATTACH_ROWS[n] for n in p["rows"]]
    note = f'<p class="lede">{html.escape(p["rows_note"])}</p>' if p.get("rows_note") else ""
    body.append(f"<section><h2>Attachment points</h2>{note}{table_html(rows)}</section>")
    body.append('<p class="note">Source: <code>hardware/PRINTED-PARTS.md</code> and the CAD it quotes. Rebuild this page '
                'with <code>sh hardware/printed-parts-pages/publish.sh</code>.</p>')
    (d / "index.html").write_text(page(p["title"] + " · printed part", p["desc"], "\n".join(body), SCRIPTS))
    return d


# ---------------------------------------------------------------- scene pages (several parts in place)
#
# LICENCE RULE. The radiation shield's 3MF (pods-r1 sources.shield_3mf) has an unknown licence. Clint ruled on
# 2026-11-24 that a page holding anything derived from it (its meshes, the remixed cap and arm, renders, or numbers
# measured off them, and the pod boxes placed by remix.box_pose) may go up ONLY as `restricted` to his own login, never
# `everyone`. Every such page is in this list; publish.sh publishes these with visibility=restricted and an allow list
# of the whoami account alone, reads the settings back, and deletes the artifact if they don't match. Nothing they hold
# is ever committed: it is built into out/ (gitignored) on each run.
RESTRICTED = ["printed-pod-bracket", "printed-shield-cap", "printed-shield-stock", "printed-assembly"]

# The full assembly. The repo gives the TX box and the shield no position relative to each other on the pole, so the
# page places them with these, and says so. Both hang on the same side of the pole, facing the same way.
POLE_D = 25.4            # the pole's OD: about 1 in (Clint, 2026-11-24), inside the SS-GSG9-1 strap's 1/2-2 in range
POLE_GAP = 250.0         # ASSUMED: the shield's lowest printed point this far above the end of the TX base's top flange
POLE_BELOW = 150.0       # the pole drawn this far below the TX base's bottom flange
POLE_ABOVE = 20.0        # and this far above the top of the shield arm's upright
# The SparkFun SEN-15901 weather meter kit (weather_meter.py: bought, estimated shapes). The repo gives it no position,
# so these place it the way the kit is normally put up: its own two-tube mast, cross arm with the cups and the vane on
# top, the rain gauge on its arm lower down, level. All ASSUMED.
METER_OVERLAP = 200.0    # ASSUMED: the kit's mast foot this far below the pole's top, the mast against the pole's back
METER_CLAMPS = (40.0, 160.0)  # ASSUMED: the kit's two gear clamps (mast to pole) this far below the pole's top
METER_RAIN_BELOW = 250.0      # ASSUMED: the rain arm's top this far below the cross arm's top
METER_DRIP = 70.0        # ASSUMED: each meter cable's drip loop this far below its PG-9 gland

MESHES = HERE / "out" / "_meshes"          # main() points this at OUTDIR/_meshes
SCENE_SCRIPTS = SCRIPTS.replace("viewer.js", "assembly.js")
COL = {"tx-base": "#d8cfbd", "tx-lid-outline": "#7fb2d6", "tx-shade": "#fafaf7", "tx-clips": "#d0703c",
       "tx-bar": "#7b5cc4", "shield-arm": "#e09a3a", "shield-cap": "#d9b03a", "shield-cup": "#c6ccd2",
       "shield-stand": "#9aa3ab", "shield-plate": "#e8ecef", "pod-th-body": "#6fa67a", "pod-th-lid": "#a9d3b1",
       "pod-baro-body": "#4f86b8", "pod-baro-lid": "#9cc2e3", "pod-uv-body": "#b8577a", "pod-uv-lid": "#e0a3b9",
       "pole": "#7b8288",
       # bought, not printed: one teal family, so the kit never reads as a print
       "meter-mast": "#2f7f86", "meter-arm": "#1f6f78", "meter-cups": "#48a9a6", "meter-vane": "#66c2bd",
       "meter-rain-arm": "#1f6f78", "meter-rain": "#8fd3cc", "meter-clamps": "#b9c4c9", "meter-cables": "#22303a"}
NAMES = {"tx-base": "TX base (enclosure 4)", "tx-lid-outline": "#905 clear lid (bought; outline only)",
         "tx-shade": "lid shade", "tx-clips": "EVM front clips", "tx-bar": "retention bar",
         "shield-arm": "remixed L-arm (pod bracket)", "shield-cap": "remixed top cap", "shield-cup": "shield base cup",
         "shield-stand": "shield stand", "shield-plate": "louver plates (6)", "pod-th-body": "TH pod body",
         "pod-th-lid": "TH pod lid", "pod-baro-body": "BARO pod body", "pod-baro-lid": "BARO pod lid",
         "pod-uv-body": "UV crown body", "pod-uv-lid": "UV crown lid (dome)", "pole": "pole (plain cylinder, about 1 in)",
         "meter-mast": "mast (two tubes)", "meter-arm": "cross arm (center-mount armature)",
         "meter-cups": "anemometer (wind cups)", "meter-vane": "wind vane", "meter-rain-arm": "rain gauge arm",
         "meter-rain": "rain gauge (tipping bucket)", "meter-clamps": "gear clamps (mast to pole)",
         "meter-cables": "RJ11 cables to the TX box's PG-9 glands"}
METER_GROUP = "Bought, not printed: SparkFun SEN-15901 weather meter kit (estimated shapes)"
METER_KEYS = ("meter-mast", "meter-arm", "meter-cups", "meter-vane", "meter-rain-arm", "meter-rain", "meter-clamps",
              "meter-cables")
TX_EXPLODE = {"tx-lid-outline": 70, "tx-clips": 110, "tx-bar": 140, "tx-shade": 190}   # mm along -Y, out of the lid
EYE = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]


def run_meshes(mode, params=None):
    d = MESHES / mode
    if d.exists():
        shutil.rmtree(d)
    if params is not None:
        d.mkdir(parents=True)
        (d / "params.json").write_text(json.dumps(params, indent=1))
    subprocess.run([sys.executable, "-B", str(HERE / "meshes.py"), mode, str(d)], check=True)
    return json.loads((d / f"{mode}.json").read_text())


def read_stl(path):
    b = Path(path).read_bytes()
    n = struct.unpack("<I", b[80:84])[0]
    assert len(b) == 84 + 50 * n, f"{path}: not a binary STL"
    rec = np.frombuffer(b[84:], dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    return rec["v"].reshape(-1, 3).astype(float), n


def entry(key, info=None, src=None, m=None, explode=(0, 0, 0), hidden=False, note=None, opacity=None, **kw):
    e = dict(key=key, label=kw.pop("label", NAMES.get(key, key)), color=kw.pop("color", COL.get(key, "#cccccc")),
             m=m or EYE, explode=[round(float(x), 3) for x in explode], hidden=hidden, src=src)
    if info:
        e["src"] = info["src"]
        for k in ("instances", "instance_explode"):
            if k in info:
                e[k] = info[k]
    if note:
        e["note"] = note
    if opacity is not None:
        e["opacity"] = opacity
    e.update(kw)
    return e


def scene_rail(explode=True):
    return ('<div class="rail">'
            + ('<label for="explode">take apart <input type="range" id="explode" min="0" max="1" step="0.01" value="0">'
               ' <output id="explode-v"></output></label>' if explode else '') +
            '<label for="cut"><input type="checkbox" id="cut"> cut</label>'
            '<label for="cut-at">at <input type="range" id="cut-at" min="0.01" max="0.99" step="0.01" value="0.5">'
            ' <output id="cut-v"></output></label>'
            '<label for="cut-axis">across <select id="cut-axis"><option value="x">x</option><option value="y">y</option>'
            '<option value="z">z</option></select></label>'
            '<label for="cut-flip"><input type="checkbox" id="cut-flip"> keep the other side</label>'
            '<button type="button" id="all">show all</button><button type="button" id="none">hide all</button>'
            '<button type="button" id="spin">stop turning</button><button type="button" id="reset">reset view</button>'
            '</div>')


def scene_page(out, slug, title, sub, b, desc, entries, sections, facts=(), downloads=(), view_note="", lede=None,
               explode=True):
    """A page with the scene viewer: entries go to scene.json (their STLs copied in), sections are HTML strings."""
    d = out / slug
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    restricted = slug in RESTRICTED
    meshes = []
    for e in entries:
        e = dict(e)
        src = e.pop("src")
        if src is not None:
            src = Path(src)
            name = src.name
            if not (d / name).exists():
                shutil.copy2(src, d / name)
            e["file"] = name
        meshes.append(e)
    for src, name in downloads:
        shutil.copy2(src, d / name)
    (d / "scene.json").write_text(json.dumps(dict(meshes=meshes)))
    shutil.copy2(HERE / "assembly.js", d / "assembly.js")
    body = [f'<header><a class="back" href="{HOST + INDEX}/" target="_top">&larr; all printed parts</a>'
            f'<div class="eyebrow">printed part · {html.escape(sub)}</div><h1>{html.escape(title)}</h1>{badge(b)}'
            f'<p class="lede">{html.escape(lede or desc.split(". ")[0] + ".")}</p></header>']
    if restricted:
        body.append('<p class="restricted">Restricted to Clint\'s login. This page holds shapes from the radiation '
                    'shield\'s 3MF, whose licence is unknown, so it never goes up as <code>everyone</code> and none of '
                    'it is in git.</p>')
    hint = ("Drag to turn, pinch or scroll to zoom, right-drag to pan. Tick a part in the key to show or hide it. "
            + ("&lsquo;Take apart&rsquo; pulls the parts away from each other. " if explode else "")
            + "&lsquo;Cut&rsquo; slices the view across x, y or z (mm, Z up).")
    if view_note:
        hint += " " + html.escape(view_note)
    body.append('<figure class="stage">'
                f'<div id="view" role="img" aria-label="3D model of the {html.escape(title)}; drag to turn"></div>'
                '<div id="status">loading the model…</div>' + scene_rail(explode)
                + '<div class="legend" id="legend" aria-label="Key: show or hide each part"></div>'
                f'<div class="hint">{hint}</div></figure>')
    if facts or downloads:
        fx = "".join(f'<div class="fact"><b>{html.escape(k)}</b><span>{inline(v)}</span></div>' for k, v in facts)
        dls = "".join(f'<a class="dl" href="{n}" download>Download {n}</a>' for _s, n in downloads)
        body.append((f'<section class="facts" aria-label="Key facts">{fx}</section>' if facts else "")
                    + (f'<div style="display:flex;flex-wrap:wrap;gap:10px">{dls}</div>' if dls else ""))
    body += sections
    body.append('<p class="note">Source: <code>hardware/PRINTED-PARTS.md</code> and the CAD it quotes. Rebuild this page '
                'with <code>sh hardware/printed-parts-pages/publish.sh</code>.</p>')
    (d / "index.html").write_text(page(title + " · printed part", desc, "\n".join(body), SCENE_SCRIPTS))
    return d


def attach_section(rows, original=False, note=""):
    src = ATTACH_ORIG if original else ATTACH_ROWS
    t = ATTACH_HEAD + [src[n] for n in rows]
    return (f'<section><h2>Attachment points</h2>{f"<p class=lede>{html.escape(note)}</p>" if note else ""}'
            f'{table_html(t)}</section>')


def checks_section(title, lines, cmd):
    return (f'<section><h2>{html.escape(title)}</h2><p class="lede">Printed by <code>{html.escape(cmd)}</code> when '
            f'this page was built.</p><pre><code>{html.escape(chr(10).join(lines))}</code></pre></section>')


def by_key(info):
    out = {}
    for e in info["meshes"]:
        e = dict(e)
        e["src"] = MESHES / {"hung": "tx", "shield": "shield", "world": "meter"}[e["frame"]] / e["file"]
        out[e["key"]] = e
    return out


def size(e):
    return " x ".join(f"{h - l:.1f}" for l, h in zip(e["lo"], e["hi"]))


def tx_base_page(out, tx):
    k = by_key(tx)
    gate = ", ".join(f"`{g}`" for g in tx["gate"]) or "none"
    ents = [entry("tx-base", k["tx-base"])]
    for key in ("tx-clips", "tx-bar", "tx-shade", "tx-lid-outline"):
        ents.append(entry(key, k[key], explode=[0, -TX_EXPLODE[key], 0], hidden=key in ("tx-shade", "tx-lid-outline"),
                          note="its own page" if key != "tx-lid-outline" else None,
                          opacity=0.35 if key == "tx-lid-outline" else None))
    b = k["tx-base"]
    facts = [("Material", "PETG (the `cage.py` header)"), ("Envelope (mm, as hung: across x up the pole x deep)", size(b)),
             ("Volume, mass", f"{b['cm3']:.1f} cm³, about {b['cm3'] * 1.27:.0f} g solid"), ("Quantity", "1"),
             ("Status", f"settled, but the STL is gated: `cage.py --stl` refuses until {gate} are sourced")]
    secs = [f"<section><h2>Features of the base, not separate prints</h2>{md_html(section('## Features of the base, not separate prints'))}</section>",
            '<section><h2>Interfaces on the base</h2><p class="lede">From PRINTED-PARTS.md (box frame, mm).</p>'
            + table_html(BASE_IF) + "</section>",
            attach_section([1, 2, 4, 6, 7, 8, 9, 10, 11, 12, 13, 25])]
    return scene_page(out, "printed-tx-base", "TX base (enclosure 4)", "tx-stack-r1 · cage.py",
                      ("no", "gated: " + ", ".join(tx["gate"]) + " (no print file)"),
                      "The printed TX box itself, enclosure 4 with its two fixes: walls, lip, corner blocks, slots, "
                      "ledges, tray and flanges. Preview 3D view and numbers.", ents, secs, facts,
                      view_note="A preview built here from cage.py's shell_solid() and its moulded parts through "
                                "true_frame(), hung as on the pole (Z up, the lid toward -y). There's no download: the "
                                "base's STL is gated, and this mesh isn't a print file.")


RETIRED = [(HW / "tx-stack-r1/cage/stl/rim-coupon.stl", "rim corner coupon r8"),
           (HW / "tx-stack-r1/cage/stl/rim-edge-long.stl", "rim edge strip, long"),
           (HW / "tx-stack-r1/cage/stl/rim-edge-short.stl", "rim edge strip, short")] + \
          [(HW / f"pods-r1/box/v1/pod-{n}-{p}.stl", f"pod box v1: {n.upper()} {p}")
           for n in ("th", "baro", "uv") for p in ("body", "lid")]


def retired_page(out):
    ents, x = [], {0: 0.0, 1: 0.0}
    pal = ["#c9c2b4", "#b4bdc4", "#c4b4bd"]
    for i, (src, label) in enumerate(RETIRED):
        v, _n = read_stl(src)
        lo, hi = v.min(0), v.max(0)
        row = int(src.parent.name == "v1")             # the rim tests in one row, the v1 boxes in the row in front
        m = [1, 0, 0, x[row] - lo[0], 0, 1, 0, -(lo[1] + hi[1]) / 2 - 220.0 * row, 0, 0, 1, -lo[2]]
        x[row] += hi[0] - lo[0] + 15.0
        key = "retired-" + src.parent.name + "-" + src.stem
        e = entry(key, src=src, m=m, label=label, color=pal[i % 3] if i < 3 else ("#cfc8b6" if "body" in label else "#b9c8d0"))
        ents.append(e)
    # v1 STLs share names with the current ones: copy them under their own names
    d = out / "_retired"
    d.mkdir(parents=True, exist_ok=True)
    for e, (src, _l) in zip(ents, RETIRED):
        dst = d / (("v1-" if src.parent.name == "v1" else "") + src.name)
        shutil.copy2(src, dst)
        e["src"] = dst
    secs = ['<section><h2>What these are</h2><ul>'
            '<li><code>tx-stack-r1/cage/stl/rim-coupon.stl</code>, <code>rim-edge-long.stl</code>, '
            '<code>rim-edge-short.stl</code>: earlier rim tests (the corner coupon r8 and two edge strips). The rim test '
            'ring replaced them.</li>'
            '<li><code>pods-r1/box/v1/*.stl</code>: the v1 pod boxes from Clint\'s CAD agent (2026-11-18). The current '
            'TH and BARO boxes in <code>box/stl/</code> build the same features, and the v1 UV box was replaced by the '
            'crown on 2026-11-19.</li></ul>'
            '<p>PRINTED-PARTS.md says don\'t print any of them. They stay in the repo as history, so there are no '
            'downloads here.</p></section>']
    return scene_page(out, "printed-retired", "Retired test prints and v1 pod boxes", "tx-stack-r1 · pods-r1",
                      ("no", "retired: don't print"),
                      "The STLs still in the repo that you shouldn't print: the old rim coupon and edge strips, and the "
                      "v1 pod boxes. 3D view only.", ents, secs,
                      view_note="Laid out in two rows, each as its STL lies.", explode=False)


def shield_lines(checks, start, stop=None):
    i = next(k for k, ln in enumerate(checks) if ln.startswith(start))
    j = next((k for k, ln in enumerate(checks) if stop and ln.startswith(stop) and k > i), len(checks) - 1)
    return checks[i:j]


def bracket_page(out, sh):
    k = by_key(sh)
    ents = [entry("shield-arm", k["shield-arm"])]
    for n in ("th", "baro"):
        for p in ("body", "lid"):
            key = f"pod-{n}-{p}"
            ents.append(entry(key, k[key], explode=k[key]["explode"], note="its own page"))
    ents.append(entry("shield-cup", k["shield-cup"], hidden=True))
    a, pose = k["shield-arm"], sh["poses"]["arm_remixed"]
    facts = [("Material", "not stated in the code"),
             ("Envelope (mm, print pose)", " x ".join(f"{x:.1f}" for x in pose["size"])),
             ("Volume, mass", f"{a['cm3']:.1f} cm³, about {a['cm3'] * 1.27:.0f} g solid"),
             ("Triangles", str(pose["tris"])), ("Quantity", "1"),
             ("Status", "LOCAL-ONLY in the doc: the STL is built from the shield's 3MF and never goes in git")]
    lines = shield_lines(sh["checks"], "arm:", "TH to BARO") + shield_lines(sh["checks"], "TH lead", "remix:")
    secs = [f"<section><h2>From PRINTED-PARTS.md</h2>{md_html(section('### Remixed L-arm'), hshift=1)}</section>",
            checks_section("Checks and their numbers", lines + [sh["checks"][-1]], "remix.py: remix_checks()"),
            attach_section([17, 24], original=True)]
    return scene_page(out, "printed-pod-bracket", "Pod bracket (remixed L-arm)", "pods-r1 · shield/remix.py",
                      ("test", "local only: build with remix.py"),
                      "The shield's L-arm with a face for the TH box and one for the BARO box, on the pole mount the "
                      "radiation shield uses. 3D view, numbers and its STL.", ents, secs, facts,
                      downloads=[(MESHES / "shield/arm_remixed.stl", "arm_remixed.stl")],
                      view_note="Shown in the shield frame (Z up, the pole behind the upright at -y), with the TH and "
                                "BARO boxes where remix.box_pose() puts them. The download is in its print pose, on the "
                                "upright's back face.")


def cap_page(out, sh):
    k = by_key(sh)
    ents = [entry("shield-cap", k["shield-cap"])]
    for p in ("body", "lid"):
        key = f"pod-uv-{p}"
        ents.append(entry(key, k[key], explode=[0, 0, k[key]["explode"][2] - 160], note="its own page"))
    ents.append(entry("shield-plate", k["shield-plate"], hidden=True))
    c, pose = k["shield-cap"], sh["poses"]["cap_remixed"]
    facts = [("Material", "not stated in the code"),
             ("Envelope (mm, print pose)", " x ".join(f"{x:.1f}" for x in pose["size"])),
             ("Volume, mass", f"{c['cm3']:.1f} cm³, about {c['cm3'] * 1.27:.0f} g solid"),
             ("Triangles", str(pose["tris"])), ("Quantity", "1"),
             ("Status", "LOCAL-ONLY in the doc: the STL is built from the shield's 3MF and never goes in git")]
    secs = [f"<section><h2>From PRINTED-PARTS.md</h2>{md_html(section('### Remixed top cap'), hshift=1)}</section>",
            checks_section("Checks and their numbers", shield_lines(sh["checks"], "cap:", "arm:") + [sh["checks"][-1]],
                           "remix.py: remix_checks()"),
            attach_section([23], original=True)]
    return scene_page(out, "printed-shield-cap", "Shield top cap (remixed)", "pods-r1 · shield/remix.py",
                      ("test", "local only: build with remix.py"),
                      "The shield's top cap with a skirt and four screw bosses that carry the UV crown. 3D view, "
                      "numbers and its STL.", ents, secs, facts,
                      downloads=[(MESHES / "shield/cap_remixed.stl", "cap_remixed.stl")],
                      view_note="Shown in the shield frame with the UV crown on it. The louver plates are in the key "
                                "(hidden to start). The download is in its print pose, on its flat top.")


def stock_page(out, sh):
    k = by_key(sh)
    ents = [entry("shield-cup", k["shield-cup"], explode=[0, 0, 15]),
            entry("shield-stand", k["shield-stand"], explode=[0, 0, 35]),
            entry("shield-plate", k["shield-plate"])]
    rows = [("shield base cup (object_67)", k["shield-cup"]), ("shield stand (object_68)", k["shield-stand"]),
            ("louver plate (object_79), print 6", k["shield-plate"])]
    t = ["| Part | Envelope in place (mm) | Volume | Triangles |", "|---|---|---|---|"]
    t += [f"| {n} | {size(e)} | {e['cm3']:.2f} cm³ | {e['tris']} |" for n, e in rows]
    secs = ['<section><h2>What these are</h2><p>The rest of the radiation shield: Clint\'s 3MF '
            '(<code>sources.shield_3mf</code>) as he got it, unchanged. Print them from the 3MF. They\'re here so every '
            'print in the station has a page. <code>shield/assemble.py</code> stacks them from their mating features: '
            'the cup\'s foot in the arm\'s pocket, the stand on the cup\'s disc, each plate\'s posts on the one below '
            '(15 mm pitch), and the cap on plate 6.</p>' + table_html(t) + "</section>"]
    return scene_page(out, "printed-shield-stock", "Shield cup, stand and louver plates", "the shield 3MF, unchanged",
                      ("ok", "print from the 3MF as supplied"),
                      "The shield parts we don't change: the base cup, the stand and six louver plates, stacked as "
                      "assemble.py places them. 3D view only.", ents, secs,
                      view_note="Shown in the shield frame. No downloads: print these from Clint's 3MF.")


def assembly_page(out, tx, sh):
    kt, ks = by_key(tx), by_key(sh)
    r = POLE_D / 2
    yb = sh["upright_back_y"]
    m_tx = [1, 0, 0, 0, 0, 1, 0, -r, 0, 0, 1, 0]                 # hung frame: back face on the pole's surface
    dz = tx["flange_z"][1] + POLE_GAP - sh["lowest_z"]
    m_sh = [-1, 0, 0, 0, 0, -1, 0, yb - r, 0, 0, 1, dz]         # shield frame turned 180 about the pole, raised dz
    ents = []
    for key in ("tx-base", "tx-lid-outline", "tx-shade", "tx-clips", "tx-bar"):
        ents.append(entry(key, kt[key], m=m_tx, explode=[0, -TX_EXPLODE.get(key, 0), 0],
                          opacity=0.35 if key == "tx-lid-outline" else None))
    for key in ("shield-arm", "pod-th-body", "pod-th-lid", "pod-baro-body", "pod-baro-lid", "shield-cup",
                "shield-stand", "shield-plate", "shield-cap", "pod-uv-body", "pod-uv-lid"):
        e = ks[key]
        ex = e["explode"]
        ents.append(entry(key, e, m=m_sh, explode=[-ex[0], -ex[1], ex[2]]))
    top = dz + max(e["hi"][2] for e in sh["meshes"] if e["key"] == "shield-arm")
    z0, z1 = tx["flange_z"][0] - POLE_BELOW, top + POLE_ABOVE
    for e in ents:
        e["group"] = "Context: bought, drawn for scale" if e["key"] == "tx-lid-outline" else "Printed parts"
    ents.append(entry("pole", None, explode=[0, 0, 0], metal=True, group="Context: bought, drawn for scale",
                      cylinder=dict(r=r, z0=round(z0, 2), z1=round(z1, 2), x=0, y=0)))
    # the SparkFun kit, in this page's frame (weather_meter.py); its cables end at the TX box's WIND and RAIN glands
    glands = {k: [g[0], g[1] - r, g[2]] for k, g in tx["glands"].items()}
    mt = run_meshes("meter", dict(pole_r=r, pole_top=z1, mast_overlap=METER_OVERLAP, mast_clamps=list(METER_CLAMPS),
                                  rain_below=METER_RAIN_BELOW, glands=glands, drip=METER_DRIP))
    km = by_key(mt)
    mex = {"meter-cups": [0, 0, 120], "meter-vane": [0, 0, 120], "meter-arm": [0, 0, 60], "meter-rain": [0, 60, 40],
           "meter-rain-arm": [0, 30, 0], "meter-clamps": [60, 0, 0]}
    for key in METER_KEYS:
        ents.append(entry(key, km[key], explode=mex.get(key, [0, 0, 0]), group=METER_GROUP, bought=True,
                          metal=key in ("meter-mast", "meter-clamps")))
    md, mi = mt["dims"], {e["key"]: e["info"] for e in mt["meshes"]}
    zm0, zm1 = mi["meter-mast"]["z"]
    facts = [("Pole", f"a plain cylinder, Ø{POLE_D:g} (about 1 in), Z {z0:.0f} to {z1:.0f}"),
             ("TX box", "back face on the pole, flanges centred on it, lid facing -y (cage.py frames)"),
             ("Shield", f"upright's back face on the pole, raised so its lowest printed point is {POLE_GAP:g} mm above "
                        "the TX base's top flange (assumed)"),
             ("Weather meter (bought)", f"the kit's mast Z {zm0:.0f} to {zm1:.0f} against the pole's back, cross arm "
                                        f"at Z {mi['meter-arm']['z']:.0f}, rain arm top at Z {mi['meter-rain-arm']['z']:.0f}"
                                        " (assumed positions, estimated shapes)"),
             ("RJ11 runs as drawn", f"wind {mi['meter-cables']['run_mm']['WIND'] / 1000:.2f} m, rain "
                                    f"{mi['meter-cables']['run_mm']['RAIN'] / 1000:.2f} m, gland to sensor")]
    secs = ['<section><h2>How it\'s placed</h2><ul>'
            '<li><strong>TX box.</strong> Every TX part comes from <code>cage.py</code> in its box frame and goes through '
            '<code>true_frame()</code> (the real hand), then is turned so Zb is up. The base\'s back face (Yb −3) sits on '
            'the pole\'s surface with the mounting flanges centred on the pole, as the base hangs (README: by its back, '
            'long side vertical, two hose clamps through the flange slots). The lid shade sits where '
            '<code>shade_solid()</code> builds it, 12 mm over the lid. The #905 lid is a bought part, and the repo only '
            'knows its outline, so it\'s drawn as a see-through 2 mm shell of that outline.</li>'
            '<li><strong>Shield.</strong> The cup, stand, plates and cap are where <code>assemble.py placements()</code> '
            'puts them (from their mating features). The remixed cap and arm come from <code>remix.py</code> in the same '
            'frame, and the TH, BARO and UV boxes go in by <code>remix.box_pose()</code>. remix.py puts the pole behind '
            'the arm\'s upright, so the upright\'s back face sits on the pole\'s surface here.</li>'
            '<li><strong>What the repo doesn\'t say.</strong> Nothing in the code gives the TX box and the shield a '
            'position relative to each other. The pole is Ø'
            f'{POLE_D:g} (about 1 in, Clint\'s figure). This page assumes: both on the same side of it, facing the '
            'same way; and the shield\'s lowest printed point '
            f'{POLE_GAP:g} mm above the end of the TX base\'s top flange. That gap also clears the AE1 antenna, which '
            'stands about 70 mm above the top wall. Change <code>POLE_D</code> and <code>POLE_GAP</code> in '
            '<code>build.py</code> to move them.</li>'
            '<li><strong>On the 1 in pole.</strong> Everything still fits. The TX base\'s flanges and the shield arm\'s '
            'upright sit flat on the pole, and their hose clamps get shorter: about 34 mm across as a circle round the '
            'pole and a flange, and 34-37 mm round the pole and the arm\'s gusset, so SAE size 20 clamps (19-44 mm). '
            'The arm\'s slots are only about 4 mm tall, so its band has to be that narrow. The SS-GSG9-1 bonding strap '
            'takes 1/2-2 in pipe, so it fits.</li>'
            '<li><strong>Not drawn.</strong> Clint\'s printed lid bolts (his STL isn\'t in the repo), the hose clamps, '
            'screws, glands, boards, the port and solar cables, and the antenna.</li></ul></section>',
            meter_section(md, mi, r),
            attach_section([1, 3, 4, 6, 10, 14, 17, 18, 23, 24, 25], original=True)]
    return scene_page(out, "printed-assembly", "Full printed assembly", "tx-stack-r1 · pods-r1 · shield",
                      ("test", "assembly view"),
                      "Every 3D-printed part in place on one pole: the TX box with its lid shade, clips and retention "
                      "bar, and the radiation shield with the pod bracket, the TH and BARO boxes, the remixed cap and the "
                      "UV crown, plus the SparkFun weather meter kit (bought, not printed) on its own mast.", ents, secs,
                      facts,
                      lede="Every 3D-printed part in its real position, on one pole, with the bought SparkFun weather "
                           "meter kit (teal, estimated shapes) on top.",
                      view_note="The TX box, the shield and the weather meter sit on the pole at assumed positions "
                                "(see below). The key groups the bought parts apart from the prints.")


def meter_section(md, mi, r):
    """What the page says about the SparkFun kit: where it is (assumed) and how big (estimated)."""
    gl, gw, gh = md["GAUGE"]
    fl, fw, _fd = md["FUNNEL"]
    loops = " / ".join(f"{d:g}" for d in sorted(set(mi["meter-clamps"]["loop_d"])))
    dims = [("Mast", f"two steel tubes, Ø{md['MAST_D']:g} x {md['MAST_TUBE_L']:g} each, slid together "
                     f"{md['MAST_JOIN']:g} mm"),
            ("Cross arm", f"{md['ARM_L']:g} mm tip to tip; the cups and the vane {md['SENSOR_AT']:g} mm either side "
                          "of the mast"),
            ("Anemometer", f"three Ø{md['CUP_D']:g} cups on a {md['CUP_R']:g} mm radius"),
            ("Wind vane", f"{md['VANE_L']:g} mm, tail fin to arrow tip"),
            ("Rain gauge", f"{gl:g} x {gw:g} x {gh:g} body, funnel opening {fl:g} x {fw:g}, on a "
                           f"{md['RAIN_ARM_L']:g} mm arm"),
            ("RJ11 cables", f"drawn Ø{md['CABLE_D']:g} round (they're flat)")]
    t = ["| Part | Size used here (mm, all estimated) |", "|---|---|"] + [f"| {a} | {b} |" for a, b in dims]
    return ('<section><h2>The weather meter kit (bought, not printed)</h2>'
            '<p>The SparkFun SEN-15901 kit (Argent Data Systems 80422 sensors) is drawn in teal and grouped on its own '
            'in the key, so it doesn\'t read as a print. The shapes are simple stand-ins from '
            '<code>hardware/printed-parts-pages/weather_meter.py</code>. <strong>Every size is an estimate.</strong> '
            'SparkFun\'s datasheet, Argent\'s 80422 datasheet and the hookup guide describe the parts and how they go '
            'together, but give no dimensions. The only published size is about 72.4 x 20.3 cm overall, from a '
            'retailer listing, and the sizes here are picked to fit inside that height. Measure the real kit and '
            'change the numbers in <code>weather_meter.py</code>.</p>' + table_html(t) +
            '<p>Where it goes is assumed too. The repo gives no position, so these constants in '
            '<code>build.py</code> place it the way the kit is normally put up:</p><ul>'
            f'<li><code>METER_OVERLAP</code> = {METER_OVERLAP:g}: the kit\'s mast stands against the back of the pole '
            '(the side away from the TX box and the shield), its foot this far below the pole\'s top. The cross arm '
            'sits on the mast\'s top, along x, the cups on +x and the vane on −x.</li>'
            f'<li><code>METER_CLAMPS</code> = {", ".join(f"{c:g}" for c in METER_CLAMPS)}: the kit\'s two gear clamps '
            'hold the mast to the pole this far below the pole\'s top. Round a Ø'
            f'{POLE_D:g} pole and the Ø{md["MAST_D"]:g} mast each band closes to about {loops} mm (as a circle), so '
            'check the supplied clamps reach that.</li>'
            f'<li><code>METER_RAIN_BELOW</code> = {METER_RAIN_BELOW:g}: the rain arm\'s top this far below the cross '
            'arm\'s top. The arm points out along +y, level, so the gauge is clear of the cups and the vane, as '
            'the hookup guide asks.</li>'
            f'<li><code>METER_DRIP</code> = {METER_DRIP:g}: the two RJ11 cables run down the mast and the pole\'s +x '
            'side to the TX box\'s WIND and RAIN PG-9 glands (<code>cage.GLAND_USE</code>), each with a drip loop '
            'this far below its gland. The cups\' short cable runs under the arm to the vane, which carries both on '
            'the wind cable (docs/hardware/bench-station-wiring.md section 3). The lengths drawn are in the facts '
            'above; the kit\'s own cable lengths aren\'t checked here.</li>'
            '<li>Check before you put it up: with these positions the rain gauge and the cross arm are higher than the '
            'UV crown, so they could shade part of its sky. Moving the kit up, or turning the rain arm, changes that.</li>'
            '</ul></section>')


def public_guard(out, pages):
    """Belt and braces for the licence rule: no public page may hold a shield-derived file."""
    for slug in pages:
        if slug in RESTRICTED:
            continue
        for f in (out / slug).rglob("*"):
            if f.is_file() and (re.search(r"shield|remix|3mf|arm_|cap_", f.name, re.I) or
                                f.resolve().is_relative_to((MESHES / "shield").resolve())):
                raise SystemExit(f"refusing: {f} on public page {slug} looks shield-derived")
            if f.suffix == ".stl" and f.read_bytes()[:16].startswith(b"shield-derived"):
                raise SystemExit(f"refusing: {f} on public page {slug} is shield-derived")
        sj = out / slug / "scene.json"
        if sj.exists() and re.search(r'"(shield|pod)-', sj.read_text()):
            raise SystemExit(f"refusing: {sj} names a shield-frame mesh")


def index_page(out, urls):
    d = out / INDEX
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    url = lambda slug: urls.get(slug, HOST + slug + "/")
    by_summary = {}
    for p in PARTS:
        for n in (p["summary"] if isinstance(p["summary"], list) else [p["summary"]]):
            by_summary[summary_row(n)[0]] = p
    body = ['<header><div class="eyebrow">weather station · hardware</div><h1>Printed parts</h1>'
            '<p class="lede">Every 3D-printed part for the weather station. Each part has its own page with a 3D view '
            'you can turn and cut, its numbers, and its STL where there is one. Everything comes from '
            '<code>hardware/PRINTED-PARTS.md</code>, which takes its numbers from the CAD code. Mass is solid PETG '
            'at 1.27 g/cm³, so it\'s an upper bound, and print times use 3.6 min/cm³. The printer is the Bambu H2D.'
            '</p></header>']
    cards = []
    for p in PARTS + SCENE_CARDS:
        if p["slug"] in RESTRICTED:     # name only: no badge, numbers or images from the shield on this public page
            cards.append(f'<a class="card r" href="{url(p["slug"])}" target="_top"><strong>{html.escape(p["title"])} '
                         f'(restricted)</strong><span class="m">{html.escape(p["sub"])}</span></a>')
        else:
            cards.append(f'<a class="card" href="{url(p["slug"])}" target="_top"><strong>{html.escape(p["title"])}'
                         f'</strong>{badge(p["badge"])}<span class="m">{html.escape(p["sub"])}</span></a>')
    body.append('<section><h2>The pages</h2><div class="cards">' + "".join(cards) + "</div>"
                '<p class="note">The pages marked (restricted) hold shapes from the radiation shield\'s 3MF, whose '
                'licence is unknown, so only Clint\'s login can open them.</p></section>')

    for c in SUMMARY_ROWS:
        if c.startswith(("Rim corner coupon", "Pod boxes v1")):
            by_summary[c] = dict(slug="printed-retired")

    def link_summary(k, c):
        if k == 0 and c in by_summary:
            return f'<a href="{url(by_summary[c]["slug"])}" target="_top">{inline(c)}</a>'
        return inline(c)
    srows = SUMMARY[:2] + [r for r in SUMMARY[2:] if "shield" not in cells(r)[0].lower()]
    body.append('<section><h2>Summary</h2>' + table_html(srows, link_summary)
                + '<p class="note">The shield cap and arm are built locally from a model with an unknown licence, '
                  f'so their rows are left out here. Their pages are restricted: <a href="{url("printed-shield-cap")}" '
                  f'target="_top">shield top cap (restricted)</a> and <a href="{url("printed-pod-bracket")}" '
                  'target="_top">pod bracket (restricted)</a>. The TX base has its own page too: '
                  f'<a href="{url("printed-tx-base")}" target="_top">TX base</a>.</p></section>')

    q = section("## Print queue")
    q = [("9. The remixed shield cap and arm, built locally, after the pod boxes (QCAP and QARM, restricted)."
          if ln.startswith("9.") else ln) for ln in q]
    qh = md_html(q)
    links = {"rim-ring.stl": "printed-rim-ring", "coupon.stl": "printed-base-coupon", "evm-clips.stl": "printed-evm-clips",
             "pod-uv-body.stl": "printed-uv-crown-body", "lid-shade.stl": "printed-lid-shade",
             "pod-uv-lid.stl": "printed-uv-crown-lid"}
    for f, slug in links.items():
        qh = qh.replace(f"(<code>{f}</code>", f'(<a href="{url(slug)}" target="_top"><code>{f}</code></a>', 1)
    qh = qh.replace("<strong>TH and BARO bodies and lids</strong>",
                    f'<strong>TH and BARO bodies and lids</strong> (<a href="{url("printed-pod-th")}" target="_top">TH</a>, '
                    f'<a href="{url("printed-pod-baro")}" target="_top">BARO</a>)')
    qh = qh.replace("QCAP", f'<a href="{url("printed-shield-cap")}" target="_top">cap page</a>').replace(
        "QARM", f'<a href="{url("printed-pod-bracket")}" target="_top">bracket page</a>')
    qh = qh.replace("<strong>Retention bar</strong>",
                    f'<strong><a href="{url("printed-retention-bar")}" target="_top">Retention bar</a></strong>')
    body.append("<section><h2>Print queue</h2>" + qh + "</section>")

    owners = {}
    for p in PARTS:
        for n in p["rows"]:
            if not p.get("rows_note"):
                owners.setdefault(n, []).append(p)

    def link_row(k, c):
        if k == 6:
            ps = owners.get(int(c), [])
            return ", ".join(f'<a href="{url(p["slug"])}" target="_top">{html.escape(p["short"])}</a>' for p in ps) or "-"
        return inline(c)
    arows = [ATTACH_HEAD[0] + " Part pages |", ATTACH_HEAD[1] + "---|"]
    arows += [ATTACH_ROWS[n] + f" {n} |" for n in sorted(ATTACH_ROWS)]
    body.append('<section><h2>Attachment points</h2><p class="lede">Every place one part attaches to another or to the '
                'pole. The last column goes to the pages of the printed parts in that joint.</p>'
                + table_html(arows, link_row) + "</section>")
    body.append('<p class="note">Rebuild these pages with <code>sh hardware/printed-parts-pages/publish.sh</code>.</p>')
    (d / "index.html").write_text(page("Printed parts", "Every 3D-printed part for the weather station: status, print "
                                       "queue, attachment points, and a page per part with a 3D view and its STL.",
                                       "\n".join(body)))
    return d


API = "https://artifacts.folk-fujita.ts.net/api/v1"


def curl(*args, data=None):
    r = subprocess.run(["curl", "-sS", "-m", "300", *args], input=data, capture_output=True, check=True)
    return r.stdout


def publish_one(slug, d, vis, account):
    """PUT one page folder with its visibility, then read the settings back. A restricted page whose settings don't
    read back as restricted to `account` alone is deleted at once."""
    import io
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for f in sorted(d.rglob("*")):
            if f.is_file():
                t.add(f, arcname=str(f.relative_to(d)))
    q = f"visibility={vis}" + (f"&allow={account}" if vis == "restricted" else "")
    res = json.loads(curl("-f", "-X", "PUT", f"{API}/artifacts/{slug}?{q}", "-H", "Content-Type: application/gzip",
                          "--data-binary", "@-", data=buf.getvalue()))
    got = json.loads(curl("-f", f"{API}/artifacts/{slug}"))
    ok = got["visibility"] == vis and (vis != "restricted" or got.get("allowed") == [account])
    if not ok:
        if vis == "restricted":
            curl("-X", "DELETE", f"{API}/artifacts/{slug}?forever=1")
            raise SystemExit(f"{slug}: settings read back as {got['visibility']} {got.get('allowed')}, not restricted "
                             f"to {account}: deleted it")
        raise SystemExit(f"{slug}: visibility read back as {got['visibility']}, wanted {vis}")
    url = res["url"]
    bad = []
    for f in sorted(d.rglob("*")):
        if f.is_file():
            rel = f.relative_to(d).as_posix()
            code = curl("-o", "/dev/null", "-w", "%{http_code}", url + ("" if rel == "index.html" else rel)).decode()
            if code != "200":
                bad.append(f"{rel} {code}")
    print(f"published v{res['version']} {url}  visibility {got['visibility']}"
          + (f" allowed {got.get('allowed')}" if vis == "restricted" else "") + ("  BAD: " + ", ".join(bad) if bad else
                                                                                  "  (every file 200)"))
    if bad:
        raise SystemExit(f"{slug}: files not served: {bad}")
    return url, got


def publish(out):
    who = json.loads(curl("-f", f"{API}/whoami"))
    account = who["account"]          # the host keys grants by the canonical account (whoami login is an alias of it)
    pages = json.loads((out / "pages.json").read_text())
    urls, report = {}, []
    for pg in pages:
        url, got = publish_one(pg["slug"], out / pg["slug"], pg["visibility"], account)
        urls[pg["slug"]] = url
        report.append(dict(slug=pg["slug"], url=url, visibility=got["visibility"], allowed=got.get("allowed")))
    (out / "urls.json").write_text(json.dumps(urls, indent=1))
    index_page(out, urls)
    public_guard(out, [INDEX])
    url, got = publish_one(INDEX, out / INDEX, "everyone", account)
    report.append(dict(slug=INDEX, url=url, visibility=got["visibility"], allowed=got.get("allowed")))
    (out / "published.json").write_text(json.dumps(report, indent=1))


SCENE_CARDS = [
    dict(slug="printed-tx-base", title="TX base (enclosure 4)", sub="tx-stack-r1 · cage.py", badge=("no", "gated: no print file")),
    dict(slug="printed-pod-bracket", title="Pod bracket (remixed L-arm)", sub="pods-r1 · shield/remix.py"),
    dict(slug="printed-shield-cap", title="Shield top cap (remixed)", sub="pods-r1 · shield/remix.py"),
    dict(slug="printed-shield-stock", title="Shield cup, stand and louver plates", sub="the shield 3MF, unchanged"),
    dict(slug="printed-assembly", title="Full printed assembly", sub="every printed part on one pole"),
    dict(slug="printed-retired", title="Retired test prints and v1 pod boxes", sub="tx-stack-r1 · pods-r1",
         badge=("no", "retired: don't print")),
]


def main():
    global MESHES
    out = Path(sys.argv[1])
    urls = {}
    if "--urls" in sys.argv:
        urls = json.loads(Path(sys.argv[sys.argv.index("--urls") + 1]).read_text())
    out.mkdir(parents=True, exist_ok=True)
    MESHES = out / "_meshes"
    if "--publish" in sys.argv:
        return publish(out)
    if "--index-only" not in sys.argv:
        for p in PARTS:
            print("built", part_page(p, out))
        tx = run_meshes("tx")
        sh = run_meshes("shield")
        for d in (tx_base_page(out, tx), retired_page(out), bracket_page(out, sh), cap_page(out, sh),
                  stock_page(out, sh), assembly_page(out, tx, sh)):
            print("built", d)
        slugs = [p["slug"] for p in PARTS + SCENE_CARDS]
        assert set(RESTRICTED) <= set(slugs)
        public_guard(out, slugs + [INDEX])
        # what publish.sh reads: every page, its visibility, index last
        pages = [dict(slug=s_, visibility="restricted" if s_ in RESTRICTED else "everyone") for s_ in slugs]
        (out / "pages.json").write_text(json.dumps(pages, indent=1))
    print("built", index_page(out, urls))
    public_guard(out, [INDEX])


if __name__ == "__main__":
    main()
