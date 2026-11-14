"""Scout hatch lid, v2: drops into the shell's roof hatch. A plate that sits on the hatch rim and a
plug that locates in the opening. Eval asset for cad-parts.

v2 delta (from v1): plug clearance 0.15 -> 0.3 a side (v1 jammed after a warm day in the car).

STATUS: printed 2026-11-06, fitted, FROZEN.
Axes: scout_refs.py, modelled where it sits on the robot.
Prints upside down: the plate's top face on the bed.

Run:  python hatch_lid_v2.py
Writes hatch_lid_v2.step and stl/hatch_lid_v2.stl beside this script.
"""
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import scout_refs as R  # noqa: E402

NAME = "hatch_lid_v2"

RIM_W = 3.0                     # the shell's rim round the hatch (scout_shell_v3.py)
PLATE_T = 2.0
PLUG_CLEAR, PLUG_DEPTH = 0.3, 3.0
LEAD_IN = 0.6                   # chamfer on the plug's bottom edges

rim_top = R.ROOF_Z + R.RIM_H
yc = R.HATCH_Y
lid = (cq.Workplane("XY").box(R.HATCH_W + 2 * RIM_W, R.HATCH_L + 2 * RIM_W, PLATE_T, centered=(True, True, False))
       .translate((0, yc, rim_top)))
plug = (cq.Workplane("XY").box(R.HATCH_W - 2 * PLUG_CLEAR, R.HATCH_L - 2 * PLUG_CLEAR, PLUG_DEPTH + 0.5,
                               centered=(True, True, False))
        .edges("<Z").chamfer(LEAD_IN).translate((0, yc, rim_top - PLUG_DEPTH)))
lid = lid.union(plug)

solid = lid.val()
assert solid.isValid() and len(lid.solids().vals()) == 1
bb = solid.BoundingBox()
print(f"bbox {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f} mm, volume {solid.Volume():.2f} mm3", flush=True)

# fit check: the hatch frame (rim and roof round the opening) as a solid; the lid may only touch it
frame = (cq.Workplane("XY").box(R.HATCH_W + 2 * RIM_W, R.HATCH_L + 2 * RIM_W, R.RIM_H + 2.0, centered=(True, True, False))
         .translate((0, yc, R.ROOF_Z - 2.0))
         .cut(cq.Workplane("XY").box(R.HATCH_W, R.HATCH_L, 20, centered=(True, True, False)).translate((0, yc, 30))))
assert solid.intersect(frame.val()).Volume() < 1e-6, "lid does not drop into the hatch"
assert abs(bb.zmin - (rim_top - PLUG_DEPTH)) < 1e-6 and abs(bb.zmax - rim_top - PLATE_T) < 1e-6
print(f"fit check passed: plug {PLUG_CLEAR} a side in the opening, plate on the rim", flush=True)

(HERE / "stl").mkdir(exist_ok=True)
cq.exporters.export(lid, str(HERE / f"{NAME}.step"))
cq.exporters.export(lid, str(HERE / "stl" / f"{NAME}.stl"))
print("DONE", flush=True)
