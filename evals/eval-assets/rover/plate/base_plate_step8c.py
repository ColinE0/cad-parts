r"""Base plate step 8c: the plate rebuilt from primitives at step 8's geometry (steps 1 to 8 were
deltas on the Onshape import, archived), with the caster holes moved 10 mm back. 8a and 8b were
caster positions that tipped on the ramp. Eval asset for cad-parts.

SRC: none (primitives). Delta vs step 8: caster holes y -78 -> -88.
STATUS: printed 2026-10-03, superseded by step 9.
Axes: +x to the robot's own right, +y forward, z up; origin on the centreline, on the drive axle
line, at the plate's top face.

Run through the cad-parts runner. Writes base_plate_step8c.step and stl\base_plate_step8c.stl and
points current.json at it.
"""
from pathlib import Path

import cadquery as cq
import cq_helpers as h

HERE = Path(__file__).resolve().parent
NAME = "base_plate_step8c"

W, L, T = 96.0, 190.0, 3.0      # x, y, z
Y0 = -100.0                     # rear edge; front edge at +90
CORNER_R = 10.0
HOLES = {                       # name: (diameter, [(x, y), ...])
    "motor": (2.2, [(sx * 28.0, sy * 8.0) for sx in (1, -1) for sy in (1, -1)]),
    "sled": (3.4, [(-18.0, 62.0), (18.0, 62.0)]),
    "bumper": (3.2, [(-35.0, 82.0), (35.0, 82.0)]),
    "caster": (3.2, [(-12.0, -88.0), (12.0, -88.0)]),
    "deck": (3.2, [(sx * 40.0, sy * 60.0) for sx in (1, -1) for sy in (1, -1)]),
    "cable": (10.0, [(0.0, 20.0)]),
}

plate = (cq.Workplane("XY").box(W, L, T, centered=(True, False, False)).translate((0, Y0, -T))
         .edges("|Z").fillet(CORNER_R))
for d, pts in HOLES.values():
    plate = plate.faces(">Z").workplane(origin=(0, 0, 0)).pushPoints(pts).hole(d)

d = h.describe(plate)
print(d, flush=True)
assert d["solids"] == 1 and d["bbox_mm"] == [W, L, T], d
h.export_checked(plate, str(HERE / NAME), stl_dir="stl")
h.set_current(HERE, f"{NAME}.step", note="step 8c: rebuilt from primitives, caster holes 10 mm back")
print("DONE", flush=True)
