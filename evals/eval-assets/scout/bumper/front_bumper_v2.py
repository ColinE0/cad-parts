"""Scout front bumper, v2: a bar across the front, below the shell's nose, on two tabs that bolt up
against the base plate's underside (M3 x 10 down through the plate, nyloc nuts under the tabs).
Eval asset for cad-parts.

v2 delta (from v1): bar 6 mm lower so it catches the doorframe instead of the shell's nose.

STATUS: printed 2026-11-01, fitted, FROZEN.
Axes: scout_refs.py, modelled where it sits on the robot.
Prints on its back: the bar's rear face on the bed.

Run:  python front_bumper_v2.py
Writes front_bumper_v2.step and stl/front_bumper_v2.stl beside this script.
"""
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import scout_refs as R  # noqa: E402

NAME = "front_bumper_v2"

TAB_X, TAB_W, TAB_T = 30.0, 12.0, 3.0      # tab centres (x), tab width, tab thickness
TAB_Y0 = 70.0                              # tab's rear end, under the plate
HOLE_Y, CLEAR_D = 79.0, 3.3                # M3 clearance through each tab
BAR_W, BAR_T, BAR_Y0 = 100.0, 6.0, 92.0    # bar width (x), thickness (y), rear face (y)
BAR_Z0, BAR_Z1 = -14.0, -1.0

plate_under = -R.PLATE_T
plate_front = R.PLATE_Y0 + R.PLATE_L
assert HOLE_Y < plate_front - 3, "bumper bolts too close to the plate's front edge"

bumper = cq.Workplane("XY").add(cq.Solid.makeBox(BAR_W, BAR_T, BAR_Z1 - BAR_Z0, cq.Vector(-BAR_W / 2, BAR_Y0, BAR_Z0)))
for sx in (1, -1):
    tab = cq.Solid.makeBox(TAB_W, BAR_Y0 + 0.5 - TAB_Y0, TAB_T,
                           cq.Vector(sx * TAB_X - TAB_W / 2, TAB_Y0, plate_under - TAB_T))
    bumper = bumper.union(cq.Workplane("XY").add(tab))
    bumper = bumper.cut(cq.Workplane("XY").add(cq.Solid.makeCylinder(
        CLEAR_D / 2, TAB_T + 2, cq.Vector(sx * TAB_X, HOLE_Y, plate_under - TAB_T - 1))))

solid = bumper.val()
assert solid.isValid() and len(bumper.solids().vals()) == 1
bb = solid.BoundingBox()
print(f"bbox {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f} mm, volume {solid.Volume():.2f} mm3", flush=True)

# fit checks: tabs up against the plate's underside, nothing into the plate or the tyres
plate = dict(R.parts())["plate"]
assert solid.intersect(plate).Volume() < 1e-6, "bumper overlaps the plate"
tab_tops = [f.Center().z for f in solid.Faces() if f.geomType() == "PLANE" and f.normalAt().z > 0.999
            and f.Center().y < plate_front]
assert tab_tops and all(abs(z - plate_under) < 1e-6 for z in tab_tops), f"tabs not up against the plate: {tab_tops}"
for name, part in R.parts():
    if name.startswith("wheel"):
        assert solid.intersect(part).Volume() < 1e-6, f"bumper hits the {name}"
print("fit checks passed: tabs seated under the plate, no overlap, tyres clear", flush=True)

(HERE / "stl").mkdir(exist_ok=True)
cq.exporters.export(bumper, str(HERE / f"{NAME}.step"))
cq.exporters.export(bumper, str(HERE / "stl" / f"{NAME}.stl"))
print("DONE", flush=True)
