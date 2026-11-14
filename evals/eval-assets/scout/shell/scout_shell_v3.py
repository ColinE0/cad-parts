"""Scout top shell, v3: the body shell over the Scout's chassis. Open underneath, an arch over each
tyre, a slot across the bottom for the charging dock's contact bar, a roof hatch for the lid, a
camera window, and four corner bosses that screw it to the base plate. Eval asset for cad-parts.

v3 delta (from v2): dock slot across the bottom (34 wide, 10 tall) so the robot can drive onto the
charging dock.

STATUS: printed 2026-11-06, fitted, FROZEN.
Axes: scout_refs.py (+x to the robot's own right, +y forward, z up, plate top face at z 0).
Prints upright, open bottom on the bed.

Run:  python scout_shell_v3.py
Writes scout_shell_v3.step and stl/scout_shell_v3.stl beside this script.
"""
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import scout_refs as R  # noqa: E402

NAME = "scout_shell_v3"

W = 116.0              # outside width (x)
Y_NOSE, Y_TAIL = 90.0, -90.0
NOSE_Z = 30.0          # top of the vertical front face
ROOF_Y0 = 72.0         # nose slope meets the roof
TAIL_Y0 = -78.0        # roof meets the tail slope
TAIL_Z = 40.0          # top of the vertical rear face
H = R.ROOF_Z
WALL = 2.0
EDGE_R = 3.0           # every outside edge except round the open bottom

ARCH_CLEAR = 2.0       # radial clearance round each tyre
ARCH_R = R.WHEEL_D / 2 + ARCH_CLEAR

DOCK_SLOT_W, DOCK_SLOT_H = 34.0, 10.0    # across x, centred on y = 0

CAM_WIN_W, CAM_WIN_Z0, CAM_WIN_Z1 = 24.0, 10.0, 24.0

BOSS_D, BOSS_H, BOSS_X = 9.0, 12.0, 34.0
BOSS_Y = (84.5, -84.5)                   # centres; each boss bites 1.0 into the front or rear wall
PILOT_D, PILOT_DEPTH = 2.6, 10.0         # M3 self-tappers up through the plate

WHEEL_RUB = 1.0                          # fit check: tyre grown this much radially must clear

assert ARCH_R - R.WHEEL_D / 2 > WHEEL_RUB
assert DOCK_SLOT_W > R.DOCK_W + 4 and DOCK_SLOT_H > R.DOCK_H + 1, "dock bar needs 2 mm a side, 1 on top"


def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").add(cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0)))


def cyl(r, h, base, axis=(0, 0, 1)):
    return cq.Workplane("XY").add(cq.Solid.makeCylinder(r, h, cq.Vector(*base), cq.Vector(*axis)))


profile = [(Y_TAIL, 0.0), (Y_NOSE, 0.0), (Y_NOSE, NOSE_Z), (ROOF_Y0, H), (TAIL_Y0, H), (Y_TAIL, TAIL_Z)]
body = cq.Workplane("YZ").polyline(profile).close().extrude(W / 2, both=True)
body = body.edges(cq.selectors.BoxSelector((-W, -300, 0.5), (W, 300, 200))).fillet(EDGE_R)
shell = body.faces("<Z").shell(-WALL)

for sy in (1, -1):
    shell = shell.cut(cyl(ARCH_R, W + 10, (-W / 2 - 5, sy * R.AXLE_Y, R.AXLE_Z), (1, 0, 0)))
shell = shell.cut(box(-W / 2 - 1, W / 2 + 1, -DOCK_SLOT_W / 2, DOCK_SLOT_W / 2, -1, DOCK_SLOT_H))

rim = box(-R.HATCH_W / 2 - 3, R.HATCH_W / 2 + 3, R.HATCH_Y - R.HATCH_L / 2 - 3, R.HATCH_Y + R.HATCH_L / 2 + 3,
          H - 1, H + R.RIM_H)
shell = shell.union(rim).cut(box(-R.HATCH_W / 2, R.HATCH_W / 2, R.HATCH_Y - R.HATCH_L / 2,
                                 R.HATCH_Y + R.HATCH_L / 2, H - WALL - 1, H + R.RIM_H + 1))
shell = shell.cut(box(-CAM_WIN_W / 2, CAM_WIN_W / 2, Y_NOSE - WALL - 1, Y_NOSE + 1, CAM_WIN_Z0, CAM_WIN_Z1))
for x in (BOSS_X, -BOSS_X):
    for y in BOSS_Y:
        shell = shell.union(cyl(BOSS_D / 2, BOSS_H, (x, y, 0)))
        shell = shell.cut(cyl(PILOT_D / 2, PILOT_DEPTH + 1, (x, y, -1)))

solid = shell.val()
assert solid.isValid() and len(shell.solids().vals()) == 1
bb = solid.BoundingBox()
print(f"bbox {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f} mm, volume {solid.Volume():.1f} mm3", flush=True)
assert abs(bb.xlen - W) < 1e-6 and abs(bb.ylen - (Y_NOSE - Y_TAIL)) < 1e-6 and abs(bb.zmax - H - R.RIM_H) < 1e-6

# fit checks
parts = R.parts()
for name, part in parts:
    v = solid.intersect(part).Volume()
    assert v < 1e-6, f"shell overlaps the {name} by {v:.3f} mm3"
for sx in (1, -1):
    for sy in (1, -1):
        rub = R.wheel(sx, sy, d=R.WHEEL_D + 2 * WHEEL_RUB, w=R.WHEEL_W + 2 * WHEEL_RUB)
        assert solid.intersect(rub).Volume() < 1e-6, f"tyre grown {WHEEL_RUB} mm rubs the shell"
dock = cq.Solid.makeBox(300, R.DOCK_W + 4, R.DOCK_H + 1, cq.Vector(-150, -R.DOCK_W / 2 - 2, 0))
assert solid.intersect(dock).Volume() < 1e-6, "dock bar does not get 2 mm a side and 1 on top"
for x in (BOSS_X, -BOSS_X):
    for y in BOSS_Y:
        assert abs(x) < R.PLATE_W / 2 - 2 and R.PLATE_Y0 + 2 < y < R.PLATE_Y0 + R.PLATE_L - 2
        foot = cq.Solid.makeCylinder(BOSS_D / 2 - 0.5, 0.5, cq.Vector(x, y, 0)).cut(
            cq.Solid.makeCylinder(PILOT_D / 2 + 0.5, 0.5, cq.Vector(x, y, 0)))
        assert abs(solid.intersect(foot).Volume() - foot.Volume()) < 1e-3, f"boss ({x}, {y}) not on the plate"
print(f"fit checks passed: 0 overlap with {len(parts)} chassis parts, tyres +{WHEEL_RUB} mm clear, dock bar "
      f"clear, bosses down on the plate", flush=True)

(HERE / "stl").mkdir(exist_ok=True)
cq.exporters.export(shell, str(HERE / f"{NAME}.step"))
cq.exporters.export(shell, str(HERE / "stl" / f"{NAME}.stl"))
print("DONE", flush=True)
