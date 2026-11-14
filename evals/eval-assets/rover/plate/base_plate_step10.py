r"""Base plate step 10: the sled holes 6 mm forward so the IR boards see the line earlier, and the
cable hole opened up for the camera ribbon. Eval asset for cad-parts.

SRC: base_plate_step9.step. Delta: sled holes (D3.4) y 62 -> 68; cable hole D10 -> D14.
STATUS: printed 2026-10-30, superseded by step 10c (bowed between the motors).
Axes: as step 8c.

Run through the cad-parts runner. Writes base_plate_step10.step and stl\base_plate_step10.stl and
points current.json at it.
"""
from pathlib import Path

import cadquery as cq
import cq_helpers as h
from OCP.BRepAdaptor import BRepAdaptor_Surface

HERE = Path(__file__).resolve().parent
NAME = "base_plate_step10"
SRC = HERE / "base_plate_step9.step"

SLED_D, SLED_X = 3.4, 18.0
SLED_Y_OLD, SLED_Y_NEW = 62.0, 68.0
CABLE_XY, CABLE_D_NEW = (0.0, 20.0), 14.0

parent = cq.importers.importStep(str(SRC)).val()
bb = parent.BoundingBox()
t = bb.zlen


def plug(d, x, y):
    return cq.Workplane("XY").add(cq.Solid.makeCylinder(d / 2, t, cq.Vector(x, y, bb.zmin)))


def drill(d, x, y):
    return cq.Workplane("XY").add(cq.Solid.makeCylinder(d / 2, t + 2, cq.Vector(x, y, bb.zmin - 1)))


plate = cq.Workplane().add(parent)
for sx in (1, -1):                      # fill the old sled holes, drill the new ones
    plate = plate.union(plug(SLED_D + 0.6, sx * SLED_X, SLED_Y_OLD))
for sx in (1, -1):
    plate = plate.cut(drill(SLED_D, sx * SLED_X, SLED_Y_NEW))
plate = plate.cut(drill(CABLE_D_NEW, *CABLE_XY))

d0, d1 = h.describe(parent), h.describe(plate)
print(h.diff(d0, d1), flush=True)
assert d1["solids"] == 1 and d1["bbox_mm"] == d0["bbox_mm"]


def z_holes(shape, d):
    out = set()
    for f in shape.Faces():
        if f.geomType() == "CYLINDER":
            c = BRepAdaptor_Surface(f.wrapped).Cylinder()
            if abs(abs(c.Axis().Direction().Z()) - 1) < 1e-9 and abs(2 * c.Radius() - d) < 1e-6:
                out.add((round(c.Location().X(), 4), round(c.Location().Y(), 4)))
    return sorted(out)


assert z_holes(plate.val(), SLED_D) == [(-SLED_X, SLED_Y_NEW), (SLED_X, SLED_Y_NEW)], z_holes(plate.val(), SLED_D)
assert z_holes(plate.val(), CABLE_D_NEW) == [CABLE_XY]
h.export_checked(plate, str(HERE / NAME), stl_dir="stl")
h.set_current(HERE, f"{NAME}.step", note="step 10: sled holes 6 mm forward, cable hole D14")
print("DONE", flush=True)
