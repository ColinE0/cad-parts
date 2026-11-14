"""IR sled v16: holds the IR line board under the front of the base plate. A flange bolts up
against the plate's underside through its two sled holes (M3 x 12 down from the top, nuts in hex
pockets under the flange); a lip in front of the flange carries the board on its underside. Eval
asset for cad-parts.

v16 delta (from v15): lip 4 mm deeper so the emitters sit about 7 mm off the floor instead of 11
(the line reading was patchy at 11).

STATUS: trial, unprinted. Fit checks below last passed 2026-10-20.
Axes: rover_refs.py (z up, plate top face at z 0; the sled hangs under the plate).
Prints upside down: the flange's top face on the bed.

Run:  python ir_sled_v16.py
Writes ir_sled_v16.step and stl/ir_sled_v16.stl beside this script.
"""
import sys
from pathlib import Path

import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import rover_refs as R  # noqa: E402

NAME = "ir_sled_v16"

FLANGE_W, FLANGE_D, FLANGE_T = 52.0, 14.0, 4.0   # x, y, z; centred on the sled holes
LIP_D = 10.0                                      # y, in front of the flange
LIP_DROP = 26.0                                   # lip underside below the plate's underside
GUSSET_T, GUSSET_X = 3.0, 24.0                    # two gussets, flange to lip, outboard of the nuts
CLEAR_D = 3.3                                     # M3 clearance
NUT_AF, NUT_DEPTH = 5.7, 2.6                      # M3 nut pocket under the flange (5.5 AF + 0.2)
BOARD_PITCH, PILOT_D, PILOT_DEPTH = 30.0, 1.7, 6.0   # IR board: two M2 self-tappers up into the lip
CABLE_W, CABLE_D = 10.0, 4.0                      # cable notch at the back of the flange
FLOOR_MIN = 4.0                                   # board's emitters at least this far off the floor

assert FLANGE_W / 2 > BOARD_PITCH / 2 + PILOT_D, "board pilots off the end of the lip"
assert PILOT_DEPTH < LIP_DROP - FLANGE_T, "pilots break into the flange"
assert GUSSET_X + GUSSET_T / 2 < FLANGE_W / 2, "gusset off the end of the flange"


def box(x0, x1, y0, y1, z0, z1):
    return cq.Workplane("XY").add(cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0)))


plate = R.load_plate()
pbb = plate.BoundingBox()
under = pbb.zmin                                  # the plate's underside: the sled's seat
row = [(x, y) for x, y, d in R.holes(plate) if abs(d - R.SLED_HOLE_D) < 0.05]
assert len(row) == 2, f"expected the plate's two sled holes, found {row}"
(x0, yc), (x1, y1) = sorted(row)
assert abs(yc - y1) < 1e-6 and abs(x0 + x1) < 1e-6, f"sled holes not a centred pair: {row}"
print(f"plate {R.PLATE_STEP.name}: underside z {under:.3f}, sled holes {sorted(row)}", flush=True)
assert GUSSET_X - GUSSET_T / 2 > x1 + NUT_AF / 0.8660254 / 2 + 0.5, "gusset blocks a nut pocket"

fy0, fy1 = yc - FLANGE_D / 2, yc + FLANGE_D / 2
lip_y0, lip_y1 = fy1, fy1 + LIP_D
lip_z0 = under - LIP_DROP
sled = box(-FLANGE_W / 2, FLANGE_W / 2, fy0, fy1, under - FLANGE_T, under)
sled = sled.union(box(-FLANGE_W / 2, FLANGE_W / 2, lip_y0, lip_y1, lip_z0, under))
for sx in (1, -1):
    gusset = (cq.Workplane("YZ", origin=(sx * GUSSET_X - GUSSET_T / 2, 0, 0))
              .polyline([(fy0 + 2, under - FLANGE_T + 0.5), (lip_y0 + 0.5, under - FLANGE_T + 0.5),
                         (lip_y0 + 0.5, lip_z0 + 4)]).close().extrude(GUSSET_T))
    sled = sled.union(gusset)
for x, y in row:
    sled = sled.cut(cq.Workplane("XY").add(cq.Solid.makeCylinder(CLEAR_D / 2, FLANGE_T + 2,
                                                                 cq.Vector(x, y, under - FLANGE_T - 1))))
    sled = sled.cut(cq.Workplane("XY", origin=(x, y, under - FLANGE_T - 1))
                    .polygon(6, NUT_AF / 0.8660254).extrude(NUT_DEPTH + 1))
lip_yc = (lip_y0 + lip_y1) / 2
for sx in (1, -1):
    sled = sled.cut(cq.Workplane("XY").add(cq.Solid.makeCylinder(PILOT_D / 2, PILOT_DEPTH + 1,
                                                                 cq.Vector(sx * BOARD_PITCH / 2, lip_yc, lip_z0 - 1))))
sled = sled.cut(box(-CABLE_W / 2, CABLE_W / 2, fy0 - 1, fy0 + CABLE_D, under - FLANGE_T - 1, under + 1))

solid = sled.val()
assert solid.isValid(), "sled is not a valid solid"
assert len(sled.solids().vals()) == 1, "sled came apart"
bb = solid.BoundingBox()
print(f"bbox {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f} mm, volume {solid.Volume():.2f} mm3", flush=True)

# fit checks against the plate and the drive train
assert abs(bb.zmax - under) < 1e-6, f"not seated: sled top {bb.zmax:.4f}, plate underside {under:.4f}"
assert solid.intersect(plate).Volume() < 1e-6, "sled overlaps the plate"
mine = set()
for f in solid.Faces():
    if f.geomType() == "CYLINDER":
        c = BRepAdaptor_Surface(f.wrapped).Cylinder()
        if abs(abs(c.Axis().Direction().Z()) - 1) < 1e-9 and abs(2 * c.Radius() - CLEAR_D) < 1e-6:
            mine.add((round(c.Location().X(), 4), round(c.Location().Y(), 4)))
assert mine == {(round(x, 4), round(y, 4)) for x, y in row}, f"sled holes {sorted(mine)} not on {sorted(row)}"
off_floor = lip_z0 - R.IR_BOARD_T - R.IR_EMITTER_H - R.FLOOR_Z
assert off_floor >= FLOOR_MIN, f"IR emitters {off_floor:.2f} mm off the floor"
for name, part in R.wheels():
    assert solid.intersect(part).Volume() < 1e-6, f"sled hits the {name}"
print(f"fit checks passed: seated under the plate, no overlap, both holes on the plate's sled holes, "
      f"emitters {off_floor:.2f} mm off the floor, wheels and caster clear", flush=True)

(HERE / "stl").mkdir(exist_ok=True)
cq.exporters.export(sled, str(HERE / f"{NAME}.step"))
cq.exporters.export(sled, str(HERE / "stl" / f"{NAME}.stl"))
print("DONE", flush=True)
