"""M2.5 standoff, 11.0 mm tall, for the Pi Zero on the middle plate. Eval asset for cad-parts.

STATUS: printed 2026-09-08 (K2), fitted, FROZEN. Variants get a new file.

Run:  & run_watchdogged.ps1 -Script ".../standoff_11mm.py"
Outputs standoff_11mm.step / .stl / .png beside this script.
"""
from pathlib import Path

import cadquery as cq
import cq_helpers as h

OUT = Path(__file__).resolve().parent
NAME = "standoff_11mm"

H = 11.0          # height, mm
OD = 5.0          # outer diameter
BORE = 2.4        # M2.5 self-tap bore (nominal; print fit is a slicer matter)

assert BORE < OD - 1.2, "wall under 0.6 mm per side"

solid = cq.Workplane("XY").circle(OD / 2).extrude(H).faces(">Z").workplane().hole(BORE)
assert solid.val().isValid()
d = h.describe(solid)
print(d, flush=True)
assert d["bbox_mm"] == [OD, OD, H], d["bbox_mm"]

h.export_checked(solid, str(OUT / NAME))
h.render6(solid, str(OUT / f"{NAME}.png"))
print("DONE", flush=True)
