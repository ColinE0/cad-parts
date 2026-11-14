"""Front bumper v4: a bar across the front of the Rover, on a flange that bolts down onto the base
plate's top face through its two bumper holes. Eval asset for cad-parts.

v4 delta (from v3): bar 4 -> 6 mm thick after v3 cracked on the doorframe.

STATUS: printed 2026-10-08, fitted, FROZEN.
Axes: rover_refs.py (z up, plate top face at z 0, +y forward).
Prints on its back: the bar's rear face on the bed.

Run:  python front_bumper_v4.py
Writes front_bumper_v4.step and stl/front_bumper_v4.stl beside this script.
"""
import sys
from pathlib import Path

import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import rover_refs as R  # noqa: E402

NAME = "front_bumper_v4"

FLANGE_W, FLANGE_T = 84.0, 3.0      # x, z; runs from the hole row forward to the bar
FLANGE_BACK = 6.0                   # flange behind the hole row (y)
BAR_W, BAR_T = 100.0, 6.0           # x, y
BAR_Z0, BAR_Z1 = -6.0, 16.0         # bar bottom and top
BAR_GAP = 0.5                       # bar's rear face ahead of the plate's front edge
CLEAR_D = 3.3                       # M3 clearance

plate = R.load_plate()
pbb = plate.BoundingBox()
top, front = pbb.zmax, pbb.ymax
row = [(x, y) for x, y, d in R.holes(plate) if abs(d - R.BUMPER_HOLE_D) < 0.05 and y > front - 15]
assert len(row) == 2, f"expected the plate's two bumper holes, found {row}"
yh = row[0][1]
print(f"plate {R.PLATE_STEP.name}: top z {top:.3f}, front edge y {front:.3f}, bumper holes {sorted(row)}",
      flush=True)

bar_y0 = front + BAR_GAP
flange = cq.Workplane("XY").add(cq.Solid.makeBox(FLANGE_W, bar_y0 - (yh - FLANGE_BACK) + 0.5, FLANGE_T,
                                                 cq.Vector(-FLANGE_W / 2, yh - FLANGE_BACK, top)))
bar = cq.Workplane("XY").add(cq.Solid.makeBox(BAR_W, BAR_T, BAR_Z1 - BAR_Z0, cq.Vector(-BAR_W / 2, bar_y0, BAR_Z0)))
bumper = flange.union(bar)
for x, y in row:
    bumper = bumper.cut(cq.Workplane("XY").add(cq.Solid.makeCylinder(CLEAR_D / 2, FLANGE_T + 2,
                                                                     cq.Vector(x, y, top - 1))))
solid = bumper.val()
assert solid.isValid() and len(bumper.solids().vals()) == 1

# fit checks
bb = solid.BoundingBox()
flange_bottom = min(f.Center().z for f in solid.Faces() if f.geomType() == "PLANE" and f.normalAt().z < -0.999
                    and abs(f.Center().y - yh) < FLANGE_BACK)
assert abs(flange_bottom - top) < 1e-6, f"flange not seated on the plate top ({flange_bottom:.4f} vs {top:.4f})"
assert solid.intersect(plate).Volume() < 1e-6, "bumper overlaps the plate"
mine = set()
for f in solid.Faces():
    if f.geomType() == "CYLINDER":
        c = BRepAdaptor_Surface(f.wrapped).Cylinder()
        if abs(abs(c.Axis().Direction().Z()) - 1) < 1e-9 and abs(2 * c.Radius() - CLEAR_D) < 1e-6:
            mine.add((round(c.Location().X(), 4), round(c.Location().Y(), 4)))
assert mine == {(round(x, 4), round(y, 4)) for x, y in row}, f"bumper holes {sorted(mine)} not on {sorted(row)}"
for name, part in R.wheels():
    assert solid.intersect(part).Volume() < 1e-6, f"bumper hits the {name}"
print(f"bbox {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f} mm; fit checks passed: seated, no overlap, "
      f"both holes on the plate's bumper holes, wheels clear", flush=True)

(HERE / "stl").mkdir(exist_ok=True)
cq.exporters.export(bumper, str(HERE / f"{NAME}.step"))
cq.exporters.export(bumper, str(HERE / "stl" / f"{NAME}.stl"))
print("DONE", flush=True)
