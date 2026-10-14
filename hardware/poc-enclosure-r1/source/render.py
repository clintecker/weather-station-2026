"""Shaded preview PNGs of the R1 parts and the assembled radiation shield (matplotlib, no GUI).

Run after build.py:  .venv-cad/bin/python hardware/poc-enclosure-r1/source/render.py
"""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from stl import mesh

ROOT = Path(__file__).resolve().parents[1]
PARTS, DOCS = ROOT / 'parts', ROOT / 'docs'
DOCS.mkdir(exist_ok=True)
LIGHT = np.array([0.4, -0.5, 0.85]) / np.linalg.norm([0.4, -0.5, 0.85])


def load(name):
    return mesh.Mesh.from_file(str(PARTS / f'{name}.stl')).vectors.copy()


def rot(tris, axis, deg):
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    m = {'x': [[1, 0, 0], [0, c, -s], [0, s, c]],
         'y': [[c, 0, s], [0, 1, 0], [-s, 0, c]],
         'z': [[c, -s, 0], [s, c, 0], [0, 0, 1]]}[axis]
    return tris @ np.array(m).T


def draw(groups, path, elev=24, azim=-58, title=None):
    fig = plt.figure(figsize=(7, 6), dpi=130)
    ax = fig.add_subplot(projection='3d')
    allpts = []
    for tris, rgb in groups:
        n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        shade = 0.35 + 0.65 * np.clip(n @ LIGHT, 0, 1)
        colors = np.clip(np.outer(shade, rgb), 0, 1)
        ax.add_collection3d(Poly3DCollection(tris, facecolors=colors, edgecolors='none'))
        allpts.append(tris.reshape(-1, 3))
    pts = np.vstack(allpts)
    lo, hi = pts.min(0), pts.max(0)
    mid, span = (lo + hi) / 2, (hi - lo).max() / 2
    for setlim, m in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), mid):
        setlim(m - span, m + span)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    if title:
        ax.set_title(title, fontsize=10)
    fig.savefig(path, bbox_inches='tight', facecolor='white')
    plt.close(fig)


WHITE, GREY, GREEN, STEEL = (0.93, 0.93, 0.9), (0.6, 0.62, 0.6), (0.25, 0.55, 0.35), (0.55, 0.58, 0.62)

for name, rgb in [('shield-louvre', WHITE), ('shield-cap', WHITE), ('shield-sensor-cartridge', GREY),
                  ('shield-arm', WHITE), ('electronics-chassis', GREY), ('nucleo-rail-coupon', GREY)]:
    draw([(load(name), rgb)], DOCS / f'{name}.png', title=f'{name} (print orientation)')

# Assembled shield: 7 louvres, cap, arm on top, cartridge hanging under the cap, three M4 rods.
PITCH = 22.0
groups = []
louvre = load('shield-louvre')
for k in range(7):
    groups.append((louvre + [0, 0, k * PITCH], WHITE))
groups.append((load('shield-cap') + [0, 0, 7 * PITCH], WHITE))
groups.append((load('shield-arm') + [0, 0, 8 * PITCH], WHITE))
cart = rot(load('shield-sensor-cartridge'), 'y', 90)       # paddle axis → straight down
cart = rot(cart, 'z', 90) + [0, -7, 7 * PITCH]             # tab holes onto the cap boss holes
groups.append((cart, GREEN))
for a in (90, 210, 330):
    x, y = 50 * np.cos(np.radians(a)), 50 * np.sin(np.radians(a))
    rod = []
    for i in range(12):
        t0, t1 = 2 * np.pi * i / 12, 2 * np.pi * (i + 1) / 12
        p = [[x + 2 * np.cos(t), y + 2 * np.sin(t)] for t in (t0, t1)]
        rod += [[[*p[0], -4], [*p[1], -4], [*p[1], 8 * PITCH + 12]],
                [[*p[0], -4], [*p[1], 8 * PITCH + 12], [*p[0], 8 * PITCH + 12]]]
    groups.append((np.array(rod), STEEL))
draw(groups, DOCS / 'shield-assembly.png', elev=12, azim=-60, title='Radiation shield, assembled')
cut = [(g[g[:, :, 1].max(1) < 0], c) for g, c in groups]  # front half removed to show the cartridge
draw([c for c in cut if len(c[0])], DOCS / 'shield-assembly-section.png', elev=8, azim=-90,
     title='Shield section: SHT45 cartridge hanging under the cap')
print('rendered', sorted(p.name for p in DOCS.glob('*.png')))
