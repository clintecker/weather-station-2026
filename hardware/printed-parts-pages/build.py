"""Build one page per printed part, plus the index, from hardware/PRINTED-PARTS.md and the committed STLs.
Run with the CAD venv:  .venv-cad/bin/python -B build.py OUTDIR [--urls urls.json]   (publish.sh does this)
Writes OUTDIR/<slug>/ (index.html, viewer.js, part.json, the STLs) for every part, and OUTDIR/printed-parts/.
--urls: the {slug: url} map the host returned when the part pages went up; the index links to those.

Only our own CAD goes on these pages. The radiation shield's 3MF has an unknown licence, so nothing derived from it
(cap or arm remix meshes, renders, or numbers from remix.py) is shown: the shield's sections are skipped, and the
attachment rows that touch the remixed cap and arm are rewritten to show only our side.
"""
import html
import json
import re
import shutil
import sys
from pathlib import Path

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
NOT_SHOWN = "the shield {} (built locally, not shown)"

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
ATTACH_ROWS = {}
for r in ATTACH[2:]:
    c = cells(r)
    n = int(c[0])
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
            '<p class="lede">Every 3D-printed part for the weather station except the TX base itself. Each part has '
            'its own page with a 3D view you can turn and cut, its numbers, and its STL. Everything comes from '
            '<code>hardware/PRINTED-PARTS.md</code>, which takes its numbers from the CAD code. Mass is solid PETG '
            'at 1.27 g/cm³, so it\'s an upper bound, and print times use 3.6 min/cm³. The printer is the Bambu H2D.'
            '</p></header>']
    cards = []
    for p in PARTS:
        cards.append(f'<a class="card" href="{url(p["slug"])}" target="_top"><strong>{html.escape(p["title"])}</strong>'
                     f'{badge(p["badge"])}<span class="m">{html.escape(p["sub"])}</span></a>')
    body.append('<section><h2>The pages</h2><div class="cards">' + "".join(cards) + "</div></section>")

    def link_summary(k, c):
        if k == 0 and c in by_summary:
            return f'<a href="{url(by_summary[c]["slug"])}" target="_top">{inline(c)}</a>'
        return inline(c)
    srows = SUMMARY[:2] + [r for r in SUMMARY[2:] if "shield" not in cells(r)[0].lower()]
    body.append('<section><h2>Summary</h2>' + table_html(srows, link_summary)
                + '<p class="note">The shield cap and arm are built locally from a model with an unknown licence, '
                  'so they aren\'t shown on these pages.</p></section>')

    q = section("## Print queue")
    q = [("9. The shield cap and arm, built locally (not shown here), after the pod boxes." if ln.startswith("9.") else ln)
         for ln in q]
    qh = md_html(q)
    links = {"rim-ring.stl": "printed-rim-ring", "coupon.stl": "printed-base-coupon", "evm-clips.stl": "printed-evm-clips",
             "pod-uv-body.stl": "printed-uv-crown-body", "lid-shade.stl": "printed-lid-shade",
             "pod-uv-lid.stl": "printed-uv-crown-lid"}
    for f, slug in links.items():
        qh = qh.replace(f"(<code>{f}</code>", f'(<a href="{url(slug)}" target="_top"><code>{f}</code></a>', 1)
    qh = qh.replace("<strong>TH and BARO bodies and lids</strong>",
                    f'<strong>TH and BARO bodies and lids</strong> (<a href="{url("printed-pod-th")}" target="_top">TH</a>, '
                    f'<a href="{url("printed-pod-baro")}" target="_top">BARO</a>)')
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


def main():
    out = Path(sys.argv[1])
    urls = {}
    if "--urls" in sys.argv:
        urls = json.loads(Path(sys.argv[sys.argv.index("--urls") + 1]).read_text())
    out.mkdir(parents=True, exist_ok=True)
    if "--index-only" not in sys.argv:
        for p in PARTS:
            print("built", part_page(p, out))
    print("built", index_page(out, urls))


if __name__ == "__main__":
    main()
