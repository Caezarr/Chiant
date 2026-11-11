"""Shaded previews of the exported STL files (matplotlib, no GPU needed)."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from stl import mesh

OUT = Path(__file__).parent / "out"
LIGHT = np.array([0.35, -0.5, 0.8])
LIGHT = LIGHT / np.linalg.norm(LIGHT)


def add(ax, path, color, dz=0.0, flip_lid=False):
    m = mesh.Mesh.from_file(str(path))
    v = m.vectors.copy()
    v[:, :, 2] += dz
    n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    shade = 0.35 + 0.65 * np.clip(np.abs(n @ LIGHT), 0, 1)
    cols = np.outer(shade, np.array(color))
    pc = Poly3DCollection(v, facecolors=np.clip(cols, 0, 1), edgecolors="none")
    ax.add_collection3d(pc)
    return v.reshape(-1, 3)


def scene(parts, elev, azim, name, title):
    fig = plt.figure(figsize=(9, 7), dpi=130)
    ax = fig.add_subplot(111, projection="3d")
    pts = np.vstack([add(ax, OUT / f, c, dz) for f, c, dz in parts])
    mn, mx = pts.min(0), pts.max(0)
    c, r = (mn + mx) / 2, (mx - mn).max() / 2
    ax.set_xlim(c[0] - r, c[0] + r)
    ax.set_ylim(c[1] - r, c[1] + r)
    ax.set_zlim(c[2] - r, c[2] + r)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    ax.set_title(title, fontsize=11)
    fig.savefig(OUT / name, bbox_inches="tight", facecolor="white")
    plt.close(fig)


BODY, LID, FOOT = (0.25, 0.27, 0.30), (0.55, 0.57, 0.62), (0.85, 0.45, 0.15)
scene(
    [("boring_box_body.stl", BODY, 0), ("_asm_lid.stl", LID, 0), ("_asm_foot.stl", FOOT, 0)],
    25,
    55,
    "preview_front.png",
    "Assemblé — face caméra (pare-brise) + côté USB",
)
scene(
    [("boring_box_body.stl", BODY, 0), ("_asm_lid.stl", LID, 0), ("_asm_foot.stl", FOOT, 0)],
    25,
    -125,
    "preview_back.png",
    "Assemblé — face habitacle (USB-C, LED, ouïes) + côté microSD",
)
scene(
    [("boring_box_body.stl", BODY, 0), ("_asm_lid.stl", LID, 38), ("_asm_foot.stl", FOOT, -22)],
    22,
    60,
    "preview_exploded.png",
    "Éclaté — capot / corps / pied GoPro",
)
scene([("boring_box_body.stl", BODY, 0)], 62, -70, "preview_body_inside.png", "Corps — intérieur")
scene(
    [("_asm_lid.stl", LID, 0)],
    -35,
    60,
    "preview_lid_under.png",
    "Capot — dessous (tubes de serrage)",
)
