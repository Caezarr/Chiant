"""Boring Parking Box V1 — parametric enclosure (build123d).

Target: Raspberry Pi 5 + official Active Cooler + Camera Module 3 (Wide),
printed without supports on a Bambu Lab A1 (PETG, 0.4 mm nozzle).

Coordinate system = Raspberry Pi board coordinates:
  x: 0 (microSD edge) -> 85 (USB/Ethernet edge)
  y: 0 (USB-C/HDMI edge) -> 56 (GPIO edge), camera chamber beyond y=56
  z: 0 = inner floor of the enclosure

Run:
  uv run --no-project --python 3.12 --with build123d python boring_box.py
"""

from __future__ import annotations

import math
from pathlib import Path

from build123d import (
    Align,
    Box,
    Compound,
    Cone,
    Cylinder,
    Location,
    Pos,
    Rectangle,
    RectangleRounded,
    RegularPolygon,
    Rot,
    export_step,
    export_stl,
    extrude,
)

OUT = Path(__file__).parent / "out"

# --------------------------------------------------------------------------
# Parameters (mm) — measure your parts with calipers and adjust if needed
# --------------------------------------------------------------------------
# Raspberry Pi 5
PI_L, PI_W, PI_T = 85.0, 56.0, 1.4
PI_HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]
USBC_X = 11.2  # USB-C power centre along x

# Enclosure shell
WALL = 2.4
FLOOR = 2.0
LID_T = 2.4
H_INT = 28.0  # inner height
STANDOFF = 6.0  # Pi PCB underside above the inner floor
GAP_SD = 1.5  # PCB -> inner wall, microSD side
GAP_USB = 0.8  # PCB -> inner wall, USB side (connectors sit in the window)
GAP_PWR = 2.0  # PCB -> inner wall, USB-C side (micro HDMI overhangs 1.63)
CHAMBER = 14.0  # camera chamber depth beyond the GPIO edge
R_OUT = 4.0

# Camera Module 3 Wide — values from the official drawing and STEP model
CAM_CX = 66.0  # lens centre along x
CAM_BOARD_W, CAM_BOARD_H = 25.0, 23.86
CAM_HOLE_DX = 21.0
CAM_HOLE_DZ = 12.5
CAM_HOLE_EDGE = 2.0  # hole pair nearest the edge opposite the connector
CAM_LENS_FROM_EDGE = 14.4  # lens centre, from that same edge
CAM_LENS_FROM_PCB = 8.2  # lens tip in front of the PCB front face (drawing 8.3, STEP 8.1)
CAM_BOARD_Z0 = 0.5  # lowest edge of the camera board (connector edge UP)
LENS_HOLE_D = 14.0
LENS_RECESS = 1.0  # lens tip behind the outer face

# Fasteners
M25_PILOT = 2.1  # M2.5 self-tapping into PETG
M25_CLEAR = 2.9
M25_HEAD_D, M25_HEAD_H = 5.4, 1.5
M2_PILOT = 1.7
M3_CLEAR = 3.4
M3_NUT_AF = 5.8  # across flats incl. clearance
MOUNT_PTS = [(32.5, 28.0), (52.5, 28.0)]  # GoPro foot screws (20 mm apart)

# Derived
X0, X1 = -GAP_SD, PI_L + GAP_USB  # inner cavity
Y0, Y1 = -GAP_PWR, PI_W + CHAMBER
IW, ID = X1 - X0, Y1 - Y0
OW, OD = IW + 2 * WALL, ID + 2 * WALL
CX, CY = (X0 + X1) / 2, (Y0 + Y1) / 2
PCB_BOT, PCB_TOP = STANDOFF, STANDOFF + PI_T
Y_OUT_FRONT = Y1 + WALL
CAM_PCB_FRONT_Y = Y_OUT_FRONT - LENS_RECESS - CAM_LENS_FROM_PCB
CAM_LENS_Z = CAM_BOARD_Z0 + CAM_LENS_FROM_EDGE  # connector edge is up
CAM_HOLES_Z = [CAM_BOARD_Z0 + CAM_HOLE_EDGE + CAM_HOLE_DZ, CAM_BOARD_Z0 + CAM_HOLE_EDGE]
FRONT_POSTS = [(X0 + 4.0, Y1 - 4.0), (X1 - 4.0, Y1 - 4.0)]

BOT = (Align.CENTER, Align.CENTER, Align.MIN)


def zcyl(x: float, y: float, z0: float, z1: float, r: float):
    return Pos(x, y, z0) * Cylinder(r, z1 - z0, align=BOT)


def ycyl(x: float, z: float, y0: float, y1: float, r: float):
    """Cylinder along +y."""
    return Pos(x, y0, z) * Rot(-90, 0, 0) * Cylinder(r, y1 - y0, align=BOT)


def xcyl(y: float, z: float, x0: float, x1: float, r: float):
    """Cylinder along +x."""
    return Pos(x0, y, z) * Rot(0, 90, 0) * Cylinder(r, x1 - x0, align=BOT)


def box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, z0) * Box(x1 - x0, y1 - y0, z1 - z0, align=BOT)


def cone_y(x: float, z: float, y0: float, y1: float, r0: float, r1: float):
    """Frustum along +y (lens chamfer)."""
    return Pos(x, y0, z) * Rot(-90, 0, 0) * Cone(r0, r1, y1 - y0, align=BOT)


# --------------------------------------------------------------------------
# Body
# --------------------------------------------------------------------------
def make_body():
    outer = Pos(CX, CY, -FLOOR) * extrude(RectangleRounded(OW, OD, R_OUT), H_INT + FLOOR)
    cavity = Pos(CX, CY, 0) * extrude(RectangleRounded(IW, ID, R_OUT - WALL + 0.2), H_INT + 1)
    body = outer - cavity

    # Pi standoffs
    for x, y in PI_HOLES:
        body += zcyl(x, y, 0, STANDOFF, 3.3)

    # GoPro foot: captive M3 nut bosses under the Pi
    for x, y in MOUNT_PTS:
        body += zcyl(x, y, 0, 3.2, 5.2)

    # Camera ribs (rise from the floor, tied to the front wall -> no supports)
    rib_top = max(CAM_HOLES_Z) + 3.5
    for sx in (-1, 1):
        rx = CAM_CX + sx * CAM_HOLE_DX / 2
        body += box(rx - 2.2, rx + 2.2, CAM_PCB_FRONT_Y, Y1 + 0.1, 0, rib_top)
        # the board only rests on pads around its holes
        body -= box(
            rx - 3,
            rx + 3,
            CAM_PCB_FRONT_Y - 1,
            CAM_PCB_FRONT_Y + 1.5,
            min(CAM_HOLES_Z) + 2.6,
            max(CAM_HOLES_Z) - 2.6,
        )

    # Front lid posts (full height, tied to the corners)
    for x, y in FRONT_POSTS:
        body += zcyl(x, y, 0, H_INT, 3.6)
    body = body & (Pos(CX, CY, -FLOOR) * extrude(RectangleRounded(OW, OD, R_OUT), H_INT + FLOOR))

    # ---- cuts ----
    for x, y in PI_HOLES:  # M2.5 pilots, through the floor
        body -= zcyl(x, y, -FLOOR - 1, STANDOFF + 1, M25_PILOT / 2)
    for x, y in MOUNT_PTS:  # M3 through + hex nut trap
        body -= zcyl(x, y, -FLOOR - 1, 4, M3_CLEAR / 2)
        hexagon = RegularPolygon(M3_NUT_AF / math.sqrt(3), 6)
        body -= Pos(x, y, 0.6) * extrude(hexagon, 3.0)
    for x, y in FRONT_POSTS:
        body -= zcyl(x, y, H_INT - 11, H_INT + 1, M25_PILOT / 2)
    for sx in (-1, 1):  # camera M2 pilots (horizontal)
        rx = CAM_CX + sx * CAM_HOLE_DX / 2
        for z in CAM_HOLES_Z:
            body -= ycyl(rx, z, CAM_PCB_FRONT_Y - 1, CAM_PCB_FRONT_Y + 5.5, M2_PILOT / 2)

    # Lens aperture + outward chamfer
    body -= ycyl(CAM_CX, CAM_LENS_Z, Y1 - 1, Y_OUT_FRONT + 1, LENS_HOLE_D / 2)
    body -= cone_y(
        CAM_CX,
        CAM_LENS_Z,
        Y1 + 0.4,
        Y_OUT_FRONT + 0.01,
        LENS_HOLE_D / 2,
        LENS_HOLE_D / 2 + WALL - 0.4,
    )

    # USB / Ethernet window (single opening: tolerant to port layout)
    body -= box(X1 - 1, X1 + WALL + 1, 1.0, 55.0, PCB_BOT - 0.9, PCB_BOT + 18.3)
    # USB-C power
    body -= box(USBC_X - 7, USBC_X + 7, Y0 - WALL - 1, Y0 + 1, PCB_TOP - 2.4, PCB_TOP + 5.6)
    # microSD access
    body -= box(X0 - WALL - 1, X0 + 1, 28 - 8.5, 28 + 8.5, PCB_BOT - 4.0, PCB_BOT + 0.8)
    # Exhaust slots, back wall (above the HDMI ports)
    for i in range(9):
        sx = 24 + i * 6.0
        body -= box(sx - 1.25, sx + 1.25, Y0 - WALL - 1, Y0 + 1, 14.0, 24.0)
    # Status LED (5 mm) on the cabin side
    body -= ycyl(80.0, 20.0, Y0 - WALL - 1, Y0 + 1, 5.1 / 2)
    # Floor intake slots (clear of standoffs and nut bosses)
    for i in range(6):
        sx = 12 + i * 7.0
        for y0, y1 in ((9.0, 20.0), (36.0, 47.0)):
            body -= box(sx - 1.25, sx + 1.25, y0, y1, -FLOOR - 1, 1)
    return body


# --------------------------------------------------------------------------
# Lid
# --------------------------------------------------------------------------
def make_lid():
    z0, z1 = H_INT, H_INT + LID_T
    lid = Pos(CX, CY, z0) * extrude(RectangleRounded(OW, OD, R_OUT), LID_T)

    # Locating lip
    lip_h, lip_t, clr = 2.5, 1.6, 0.25
    ring = RectangleRounded(IW - 2 * clr, ID - 2 * clr, R_OUT - WALL) - Rectangle(
        IW - 2 * (clr + lip_t), ID - 2 * (clr + lip_t)
    )
    lip = Pos(CX, CY, z0 - lip_h) * extrude(ring, lip_h)
    for x, y in FRONT_POSTS:
        lip -= zcyl(x, y, z0 - lip_h - 1, z0, 4.0)
    lid += lip

    # Clamp tubes on the Pi mounting holes
    for x, y in PI_HOLES:
        lid += zcyl(x, y, PCB_TOP + 0.15, z0, 2.8)
        # reinforcing cone at the root (tubes are 20 mm tall)
        lid += Pos(x, y, z0 - 6) * Cone(2.8, 4.4, 6, align=BOT)

    # Screws
    for x, y in PI_HOLES + FRONT_POSTS:
        lid -= zcyl(x, y, 0, z1 + 1, M25_CLEAR / 2)
        lid -= zcyl(x, y, z1 - M25_HEAD_H, z1 + 1, M25_HEAD_D / 2)

    # Fan intake grille above the Active Cooler
    for i in range(10):
        sx = 10 + i * 5.0
        lid -= box(sx - 1.1, sx + 1.1, 10.0, 46.0, z0 - 1, z1 + 1)
    return lid


# --------------------------------------------------------------------------
# GoPro-compatible foot (2 prongs), screwed under the body
# --------------------------------------------------------------------------
def make_mount():
    plate_t, prong_t, gap, prong_r, axis_h = 3.2, 3.0, 3.2, 7.5, 10.5
    foot = Pos(0, 0, 0) * extrude(RectangleRounded(36, 20, 3), plate_t)
    for sy in (-1, 1):
        yc = sy * (gap + prong_t) / 2
        prong = box(
            -prong_r, prong_r, yc - prong_t / 2, yc + prong_t / 2, plate_t, plate_t + axis_h
        )
        prong += (
            Pos(0, yc - prong_t / 2, plate_t + axis_h)
            * Rot(-90, 0, 0)
            * Cylinder(prong_r, prong_t, align=BOT)
        )
        foot += prong
    foot -= ycyl(0, plate_t + axis_h, -10, 10, 5.2 / 2)
    for sx in (-1, 1):  # M3 countersunk-ish: clearance + head recess on prong side
        foot -= zcyl(sx * 10, 0, -1, plate_t + 30, M3_CLEAR / 2)
    # relieve the prongs around the screw heads
    for sx in (-1, 1):
        foot -= zcyl(sx * 10, 0, plate_t, plate_t + 30, 3.4)
    return foot


# --------------------------------------------------------------------------
# Fit-test coupon: Pi holes + camera holes + lens, 1.2 mm thick (10 min print)
# --------------------------------------------------------------------------
def make_coupon():
    c = box(-2, 68, -2, 58, 0, 1.2)
    c -= box(8, 57, 8, 48, -1, 3)
    for x, y in PI_HOLES:
        c += zcyl(x, y, 0, 3.0, 3.0)
        c -= zcyl(x, y, -1, 4, M25_PILOT / 2)
    cam = box(72, 72 + CAM_BOARD_W + 4, 0, CAM_BOARD_H + 4, 0, 1.2)
    ox, oz = 72 + 2 + CAM_BOARD_W / 2, 2 + 9.46
    cam -= zcyl(ox, oz, -1, 3, LENS_HOLE_D / 2)
    for sx in (-1, 1):
        for dz in (0.0, CAM_HOLE_DZ):
            cam += zcyl(ox + sx * CAM_HOLE_DX / 2, oz + dz, 0, 3.0, 2.2)
            cam -= zcyl(ox + sx * CAM_HOLE_DX / 2, oz + dz, -1, 4, M2_PILOT / 2)
    return c + cam + box(66, 73, 10, 18, 0, 1.2)


def solid_report(name: str, part) -> None:
    bb = part.bounding_box()
    solids = len(part.solids())
    print(
        f"{name:8s} {bb.size.X:6.1f} x {bb.size.Y:6.1f} x {bb.size.Z:6.1f} mm  "
        f"vol {part.volume / 1000:6.1f} cm3  solids={solids}  valid={part.is_valid}"
    )


def main() -> None:
    OUT.mkdir(exist_ok=True)
    body, lid, mount, coupon = make_body(), make_lid(), make_mount(), make_coupon()
    for name, part in (("body", body), ("lid", lid), ("mount", mount), ("coupon", coupon)):
        solid_report(name, part)

    # Print orientation: body floor down, lid top face down, foot plate down
    lid_print = Rot(180, 0, 0) * (Pos(0, 0, -(H_INT + LID_T)) * lid)
    export_stl(body, str(OUT / "boring_box_body.stl"), tolerance=0.02, angular_tolerance=0.2)
    export_stl(lid_print, str(OUT / "boring_box_lid.stl"), tolerance=0.02, angular_tolerance=0.2)
    export_stl(mount, str(OUT / "boring_box_gopro_foot.stl"), tolerance=0.02, angular_tolerance=0.2)
    export_stl(
        coupon, str(OUT / "boring_box_fit_coupon.stl"), tolerance=0.02, angular_tolerance=0.2
    )

    # Assembly STEP (editable in Fusion / Bambu Studio)
    foot_asm = Location((42.5, 28, -FLOOR)) * (Rot(180, 0, 0) * mount)
    body.label, lid.label, foot_asm.label = "body", "lid", "gopro_foot"
    asm = Compound(label="boring_box_v1", children=[body, lid, foot_asm])
    export_step(asm, str(OUT / "boring_box_v1.step"))
    export_stl(lid, str(OUT / "_asm_lid.stl"), tolerance=0.05)
    export_stl(foot_asm, str(OUT / "_asm_foot.stl"), tolerance=0.05)
    print(f"outer: {OW:.1f} x {OD:.1f} x {H_INT + FLOOR + LID_T:.1f} mm")
    print(f"lens centre: x={CAM_CX} z={CAM_LENS_Z} | camera pcb front y={CAM_PCB_FRONT_Y:.1f}")


def _report(name: str, body, lid, vol, worst: list) -> None:
    b = body & vol
    l = lid & vol
    bv = b.volume if b else 0.0
    lv = l.volume if l else 0.0
    if bv > 0.01 or lv > 0.01:
        worst.append((name, bv, lv))


def check(pi_step: str | None = None, cam_step: str | None = None) -> None:
    """Interference check.

    Without arguments: simplified volumes. With the official STEP files
    (datasheets.raspberrypi.com): the bounding box of every solid of the real
    models, placed in the enclosure, is intersected with body and lid.
    """
    from build123d import import_step

    body, lid = make_body(), make_lid()
    worst: list = []
    count = 0
    if pi_step:
        for i, s in enumerate(import_step(pi_step).solids()):
            b = s.bounding_box()
            vol = box(b.min.X, b.max.X, b.min.Y, b.max.Y, PCB_BOT + b.min.Z, PCB_BOT + b.max.Z)
            _report(
                f"pi5 solid {i} x{b.min.X:.1f}..{b.max.X:.1f} y{b.min.Y:.1f}..{b.max.Y:.1f} "
                f"z{b.min.Z:.1f}..{b.max.Z:.1f}",
                body,
                lid,
                vol,
                worst,
            )
            count += 1
    else:
        _report("pcb", body, lid, box(0, PI_L, 0, PI_W, PCB_BOT, PCB_TOP), worst)
        _report("usb", body, lid, box(66.4, 88.05, 2.2, 54.3, PCB_TOP, PCB_BOT + 17.6), worst)
        _report("usb-c/hdmi", body, lid, box(6.7, 45.5, -1.63, 6.2, PCB_TOP, PCB_BOT + 4.6), worst)
        _report("microSD", body, lid, box(-2.4, 13.7, 22.1, 34.1, PCB_BOT - 1.45, PCB_BOT), worst)
        _report("gpio", body, lid, box(7, 58, 49.9, 55.1, PCB_TOP, PCB_TOP + 8.6), worst)
    _report("cooler", body, lid, box(5, 60, 10, 46, PCB_TOP, PCB_TOP + 10.5), worst)
    if cam_step:
        # camera model: x = towards connector, y = board width, -z = lens
        pcb_front_z = -0.76  # 0.02 mm clearance: the board seats on the rib pads
        for i, s in enumerate(import_step(cam_step).solids()):
            b = s.bounding_box()
            vol = box(
                CAM_CX + 12.5 - b.max.Y,
                CAM_CX + 12.5 - b.min.Y,
                CAM_PCB_FRONT_Y + (pcb_front_z - b.max.Z),
                CAM_PCB_FRONT_Y + (pcb_front_z - b.min.Z),
                CAM_BOARD_Z0 + b.min.X,
                CAM_BOARD_Z0 + b.max.X,
            )
            _report(
                f"cam solid {i} x{b.min.X:.1f}..{b.max.X:.1f} y{b.min.Y:.1f}..{b.max.Y:.1f} "
                f"z{b.min.Z:.1f}..{b.max.Z:.1f}",
                body,
                lid,
                vol,
                worst,
            )
            count += 1
    else:
        _report(
            "camera pcb",
            body,
            lid,
            box(
                CAM_CX - 12.5,
                CAM_CX + 12.5,
                CAM_PCB_FRONT_Y - 1.1,
                CAM_PCB_FRONT_Y,
                CAM_BOARD_Z0,
                CAM_BOARD_Z0 + CAM_BOARD_H,
            ),
            worst,
        )
        _report(
            "lens",
            body,
            lid,
            ycyl(CAM_CX, CAM_LENS_Z, CAM_PCB_FRONT_Y, CAM_PCB_FRONT_Y + CAM_LENS_FROM_PCB, 4.3),
            worst,
        )
    bl = body & lid
    print(f"checked {count} real solids" if count else "checked simplified volumes")
    print(f"body∩lid = {(bl.volume if bl else 0.0):.2f} mm3")
    for name, bv, lv in worst:
        print(f"  INTERFERENCE {name}: body {bv:.2f} mm3, lid {lv:.2f} mm3")
    print("no interference" if not worst else f"{len(worst)} interference(s)")


if __name__ == "__main__":
    import sys

    if "--check" in sys.argv:
        extra = [a for a in sys.argv[1:] if not a.startswith("--")]
        check(*extra[:2])
        raise SystemExit(0)
    main()
