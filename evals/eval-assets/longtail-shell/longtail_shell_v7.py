"""Longtail top shell, v7: the body shell over the Longtail robot's chassis. Open underneath, wheel
arches over all four tyres, a battery hatch in the roof, a camera window in the front face, a rear
ToF window, a rear wing on two struts, and four corner bosses that screw it to the base plate.
Eval asset for cad-parts.

v7 delta (from v6): rear wing struts 4 -> 6 mm square after v6's struts snapped in a crash; wing
chord 16 -> 20.

STATUS: printed 2026-11-02 (v7), fitted, FROZEN.
Axes: +x to the robot's own right, +y forward, z up; origin on the centreline midway between the
axles, at the base plate's top face (chassis_ref.py). Prints upright, open bottom on the bed.

Run:  python longtail_shell_v7.py
Writes longtail_shell_v7.step and stl/longtail_shell_v7.stl beside this script.
"""
from pathlib import Path

import cadquery as cq

import chassis_ref as R

HERE = Path(__file__).resolve().parent
NAME = "longtail_shell_v7"

# body envelope, side profile in the YZ plane, extruded across x
W = 130.0             # outside width (x)
Y_NOSE = 100.0        # front face
Y_TAIL = -130.0       # rear face
H = 56.0              # roof top above the plate
NOSE_Z = 34.0         # top of the vertical front face
ROOF_Y0 = 80.0        # nose slope meets the roof
TAIL_Y0 = -96.0       # roof meets the tail slope
TAIL_Z = 40.0         # top of the vertical rear face
WALL = 2.4            # walls and roof
EDGE_R = 4.0          # fillet on every outside edge except round the open bottom

# wheel arches: one cylinder per axle across the full width
ARCH_CLEAR = 3.0      # radial clearance round each tyre (v4 rubbed at 1.5 on bumps)
ARCH_R = R.WHEEL_D / 2 + ARCH_CLEAR

# battery hatch in the roof, raised rim round it for the lid to seat in
HATCH_W, HATCH_L, HATCH_Y = 70.0, 90.0, -10.0
RIM_W, RIM_H = 3.0, 2.0

# front face: camera window and two headlight recesses
CAM_WIN_W, CAM_WIN_Z0, CAM_WIN_Z1 = 28.0, 12.0, 28.0
LAMP_D, LAMP_DEPTH, LAMP_X, LAMP_Z = 10.0, 1.0, 45.0, 22.0

# side vents over the electronics, through both side walls
VENT_H, VENT_L = 3.0, 40.0
VENT_Z = (30.0, 36.0, 42.0)          # bottom of each slot

# corner bosses: M3 self-tappers come up through the base plate into them
BOSS_D, BOSS_H, BOSS_X = 10.0, 14.0, 40.0
BOSS_Y = (93.5, -123.5)              # centres; each boss bites 0.9 into the front or rear wall
PILOT_D, PILOT_DEPTH = 2.6, 12.0

# tail: stiffening ribs on the inside of the side walls
RIB_T, RIB_DEPTH, RIB_H = 2.0, 5.0, 40.0
RIB_Y = (-100.0, -115.0)

# rear wing on two struts standing on the roof
WING_W, WING_C, WING_T = 110.0, 20.0, 3.0
WING_Y, WING_Z = -88.0, 68.0         # chord centre, wing underside
STRUT, STRUT_X = 6.0, 40.0

# roof antenna boss
ANT_D, ANT_H, ANT_HOLE, ANT_X, ANT_Y = 8.0, 6.0, 3.0, 30.0, 55.0

# rear face: ToF window and a cable grommet hole
TOF_WIN_W, TOF_WIN_Z0, TOF_WIN_Z1 = 24.0, 4.0, 22.0
GROMMET_D, GROMMET_X, GROMMET_Z = 12.0, 40.0, 22.0

# badge recess on the robot's left flank, tail end
BADGE_Y0, BADGE_Y1, BADGE_Z0, BADGE_Z1, BADGE_DEPTH = -122.0, -100.0, 26.0, 34.0, 0.8

WHEEL_RUB = 1.0       # fit check: tyre grown by this much radially must still clear

assert ARCH_R - R.WHEEL_D / 2 > WHEEL_RUB, "arch clearance smaller than the rub check"
assert ARCH_R + R.AXLE_Z < H - WALL - 10, "arch crown too close to the roof"
assert BOSS_X + BOSS_D / 2 < W / 2 - WALL, "corner boss through the side wall"


def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").add(cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0)))


def cyl(r, h, base, axis):
    return cq.Workplane("XY").add(cq.Solid.makeCylinder(r, h, cq.Vector(*base), cq.Vector(*axis)))


# --- body: side profile extruded across x, every edge but the bottom rounded, then shelled ---
profile = [(Y_TAIL, 0.0), (Y_NOSE, 0.0), (Y_NOSE, NOSE_Z), (ROOF_Y0, H), (TAIL_Y0, H), (Y_TAIL, TAIL_Z)]
body = cq.Workplane("YZ").polyline(profile).close().extrude(W / 2, both=True)
body = body.edges(cq.selectors.BoxSelector((-W, -300, 0.5), (W, 300, 200))).fillet(EDGE_R)
shell = body.faces("<Z").shell(-WALL)

# --- wheel arches ---
for sy in (1, -1):
    shell = shell.cut(cyl(ARCH_R, W + 10, (-W / 2 - 5, sy * R.AXLE_Y, R.AXLE_Z), (1, 0, 0)))

# --- battery hatch and its rim ---
rim = (box(-HATCH_W / 2 - RIM_W, HATCH_W / 2 + RIM_W, HATCH_Y - HATCH_L / 2 - RIM_W,
           HATCH_Y + HATCH_L / 2 + RIM_W, H - 1.0, H + RIM_H))
shell = shell.union(rim)
shell = shell.cut(box(-HATCH_W / 2, HATCH_W / 2, HATCH_Y - HATCH_L / 2, HATCH_Y + HATCH_L / 2,
                      H - WALL - 1.0, H + RIM_H + 1.0))

# --- front face: camera window, headlight recesses ---
shell = shell.cut(box(-CAM_WIN_W / 2, CAM_WIN_W / 2, Y_NOSE - WALL - 1, Y_NOSE + 1, CAM_WIN_Z0, CAM_WIN_Z1))
for sx in (1, -1):
    shell = shell.cut(cyl(LAMP_D / 2, LAMP_DEPTH + 1, (sx * LAMP_X, Y_NOSE + 1, LAMP_Z), (0, -1, 0)))

# --- side vents ---
for z in VENT_Z:
    shell = shell.cut(box(-W / 2 - 1, W / 2 + 1, -VENT_L / 2, VENT_L / 2, z, z + VENT_H))

# --- corner bosses with pilots from below ---
for x in (BOSS_X, -BOSS_X):
    for y in BOSS_Y:
        shell = shell.union(cyl(BOSS_D / 2, BOSS_H, (x, y, 0), (0, 0, 1)))
        shell = shell.cut(cyl(PILOT_D / 2, PILOT_DEPTH + 1, (x, y, -1), (0, 0, 1)))

# --- tail ribs ---
for sx in (1, -1):
    x_in = sx * (W / 2 - WALL)
    for y in RIB_Y:
        x0, x1 = sorted((x_in + sx * 0.5, x_in - sx * RIB_DEPTH))
        shell = shell.union(box(x0, x1, y - RIB_T / 2, y + RIB_T / 2, 0, RIB_H))

# --- rear wing on its struts ---
for sx in (1, -1):
    shell = shell.union(box(sx * STRUT_X - STRUT / 2, sx * STRUT_X + STRUT / 2, WING_Y - STRUT / 2,
                            WING_Y + STRUT / 2, H - 1.0, WING_Z + 0.5))
shell = shell.union(box(-WING_W / 2, WING_W / 2, WING_Y - WING_C / 2, WING_Y + WING_C / 2,
                        WING_Z, WING_Z + WING_T))

# --- antenna boss ---
shell = shell.union(cyl(ANT_D / 2, ANT_H + 1, (ANT_X, ANT_Y, H - 1), (0, 0, 1)))
shell = shell.cut(cyl(ANT_HOLE / 2, ANT_H + 1, (ANT_X, ANT_Y, H), (0, 0, 1)))

# --- rear face: ToF window, grommet hole ---
shell = shell.cut(box(-TOF_WIN_W / 2, TOF_WIN_W / 2, Y_TAIL - 1, Y_TAIL + WALL + 1, TOF_WIN_Z0, TOF_WIN_Z1))
shell = shell.cut(cyl(GROMMET_D / 2, WALL + 2, (GROMMET_X, Y_TAIL - 1, GROMMET_Z), (0, 1, 0)))

# --- badge recess, robot's left flank ---
shell = shell.cut(box(-W / 2 - 1, -W / 2 + BADGE_DEPTH, BADGE_Y0, BADGE_Y1, BADGE_Z0, BADGE_Z1))

solid = shell.val()
assert solid.isValid(), "shell is not a valid solid"
assert len(shell.solids().vals()) == 1, "shell came apart into more than one solid"
bb = solid.BoundingBox()
print(f"bbox {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f} mm (z {bb.zmin:.2f}..{bb.zmax:.2f}), "
      f"volume {solid.Volume():.1f} mm3", flush=True)
assert abs(bb.xlen - W) < 1e-6 and abs(bb.ylen - (Y_NOSE - Y_TAIL)) < 1e-6
assert abs(bb.zmin) < 1e-6 and abs(bb.zmax - (WING_Z + WING_T)) < 1e-6

# --- fit checks against every chassis part ---
parts = R.parts()
for name, part in parts:
    v = solid.intersect(part).Volume()
    assert v < 1e-6, f"shell overlaps the {name} by {v:.3f} mm3"
for sx in (1, -1):
    for sy in (1, -1):
        rub = R.wheel(sx, sy, d=R.WHEEL_D + 2 * WHEEL_RUB, w=R.WHEEL_W + 2 * WHEEL_RUB)
        v = solid.intersect(rub).Volume()
        assert v < 1e-6, f"tyre grown {WHEEL_RUB} mm rubs the shell ({v:.3f} mm3)"
lens_axis = cyl(0.5, 20, (0, R.CAM_Y, R.CAM_Z), (0, 1, 0)).val()
assert solid.intersect(lens_axis).Volume() < 1e-6, "camera window does not clear the lens axis"
plate_x, plate_y = R.PLATE_W / 2, (R.PLATE_Y0, R.PLATE_Y0 + R.PLATE_L)
for x in (BOSS_X, -BOSS_X):
    for y in BOSS_Y:
        assert abs(x) < plate_x - 2 and plate_y[0] + 2 < y < plate_y[1] - 2, f"boss ({x}, {y}) screw misses the plate"
        foot = cq.Solid.makeCylinder(BOSS_D / 2 - 0.5, 0.5, cq.Vector(x, y, 0)).cut(
            cq.Solid.makeCylinder(PILOT_D / 2 + 0.5, 0.5, cq.Vector(x, y, 0)))
        got = solid.intersect(foot).Volume()
        assert abs(got - foot.Volume()) < 1e-3, f"boss at ({x}, {y}) does not reach the plate top"
print(f"fit checks passed: 0 overlap with {len(parts)} chassis parts, tyres +{WHEEL_RUB} mm clear, "
      f"lens sees out, four bosses down on the plate", flush=True)

(HERE / "stl").mkdir(exist_ok=True)
cq.exporters.export(shell, str(HERE / f"{NAME}.step"))
cq.exporters.export(shell, str(HERE / "stl" / f"{NAME}.stl"))
print("DONE", flush=True)
