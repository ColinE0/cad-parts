r"""Base plate step 10c: 4 mm thick instead of 3, after the flex test (the 3 mm plate bowed
between the motors). The extra 1 mm goes underneath: the top face is unchanged, so everything on
top still fits, and parts bolted underneath sit 1 mm lower. Branch of step 10 (10b was 5 mm thick:
too heavy, dropped). Eval asset for cad-parts.

SRC: base_plate_step10.step. Delta: bottom face z -3 -> -4. The plate is a prism (every hole and
slot goes through), so its top face is re-extruded 4 mm down; a 1 mm slab unioned underneath only
kissed the parent and came out invalid.
STATUS: printed 2026-11-09, on the robot.
Axes: as step 8c.

Run through the cad-parts runner. Writes base_plate_step10c.step and stl\base_plate_step10c.stl and
points current.json at it.
"""
from pathlib import Path

import cadquery as cq
import cq_helpers as h

HERE = Path(__file__).resolve().parent
NAME = "base_plate_step10c"
SRC = HERE / "base_plate_step10.step"

EXTRA = 1.0     # added under the bottom face

parent = cq.importers.importStep(str(SRC)).val()
pbb = parent.BoundingBox()
top = cq.Workplane().add(parent).faces(">Z").val()
assert abs(top.Area() * pbb.zlen - parent.Volume()) < 0.01, "parent is not a prism"
plate = cq.Workplane().add(cq.Solid.extrudeLinear(top, cq.Vector(0, 0, -(pbb.zlen + EXTRA))))

d0, d1 = h.describe(parent), h.describe(plate)
print(h.diff(d0, d1), flush=True)
assert d1["solids"] == 1 and d1["faces"] == d0["faces"] and plate.val().isValid()
assert abs(d1["bbox_min"][2] - (d0["bbox_min"][2] - EXTRA)) < 1e-6 and d1["bbox_max"][2] == d0["bbox_max"][2]
assert abs(d1["volume_mm3"] - d0["volume_mm3"] * (d0["bbox_mm"][2] + EXTRA) / d0["bbox_mm"][2]) < 0.5
h.export_checked(plate, str(HERE / NAME), stl_dir="stl")
h.set_current(HERE, f"{NAME}.step", note="step 10c: 4 mm plate, extra 1 mm underneath; printed 11-09, on the robot")
print("DONE", flush=True)
