r"""Base plate step 9: two slots for the battery's hook-and-loop strap. Eval asset for cad-parts.

SRC: base_plate_step8c.step. Delta: two 20 x 4 slots along y at x = +-30, centred on y = -30.
STATUS: printed 2026-10-16, superseded by step 10.
Axes: as step 8c.

Run through the cad-parts runner. Writes base_plate_step9.step and stl\base_plate_step9.stl and
points current.json at it.
"""
import math
from pathlib import Path

import cadquery as cq
import cq_helpers as h

HERE = Path(__file__).resolve().parent
NAME = "base_plate_step9"
SRC = HERE / "base_plate_step8c.step"

SLOT_L, SLOT_W = 20.0, 4.0
SLOT_PTS = [(-30.0, -30.0), (30.0, -30.0)]

parent = cq.importers.importStep(str(SRC)).val()
slots = (cq.Workplane("XY").workplane(offset=-10).pushPoints(SLOT_PTS)
         .slot2D(SLOT_L, SLOT_W, angle=90).extrude(20))
plate = cq.Workplane().add(parent).cut(slots)

d0, d1 = h.describe(parent), h.describe(plate)
print(h.diff(d0, d1), flush=True)
assert not h.is_noop(h.diff(d0, d1))
removed = parent.Volume() - plate.val().Volume()
t = parent.BoundingBox().zlen
want = len(SLOT_PTS) * ((SLOT_L - SLOT_W) * SLOT_W + math.pi * SLOT_W ** 2 / 4) * t
assert abs(removed - want) < 0.01 * want, (removed, want)
h.export_checked(plate, str(HERE / NAME), stl_dir="stl")
h.set_current(HERE, f"{NAME}.step", note="step 9: battery strap slots")
print("DONE", flush=True)
