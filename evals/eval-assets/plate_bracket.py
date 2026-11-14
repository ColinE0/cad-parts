"""L bracket that bolts to the plate through its two +y holes and stands 15 mm proud of the plate
top. Hole positions and the plate top are read from the plate's B-rep. Eval asset for cad-parts.

STATUS: trial, unprinted. Fit checks below last passed 2026-10-20.
Axes: the plate's own frame (z up, plate top face is the seat).

Run:  python plate_bracket.py
Outputs plate_bracket.step and plate_bracket.stl beside this script.
"""
from pathlib import Path

import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface

HERE = Path(__file__).resolve().parent
PLATE_STEP = HERE / "plate-chain-moved" / "plate_step1.step"   # the plate this bracket bolts to
NAME = "plate_bracket"

PROUD = 15.0       # bracket top above the plate top
FLANGE_T = 3.0     # flange on the plate
FLANGE_W = 10.0    # flange width in y, centred on the hole row
WALL_T = 3.0       # upright, outboard of the flange (+y side)
END = 5.0          # flange length past each hole centre in x
CLEAR_D = 3.3      # M3 clearance (ISO 273 medium, assumed)

plate = cq.importers.importStep(str(PLATE_STEP)).val()
pbb = plate.BoundingBox()
top = pbb.zmax

# the plate's through holes: cylinder faces whose axis runs along z
holes = set()
for f in plate.Faces():
    if f.geomType() != "CYLINDER":
        continue
    c = BRepAdaptor_Surface(f.wrapped).Cylinder()
    if abs(abs(c.Axis().Direction().Z()) - 1) < 1e-9:
        holes.add((round(c.Location().X(), 6), round(c.Location().Y(), 6)))
row = sorted(h for h in holes if h[1] > 0)
assert len(row) == 2, f"expected two +y holes, found {row}"
(x0, y0), (x1, y1) = row
assert abs(y0 - y1) < 1e-6
print(f"plate {PLATE_STEP.name}: top z {top:.3f}, bolting through {row}", flush=True)

flange = (cq.Workplane("XY").box(x1 - x0 + 2 * END, FLANGE_W, FLANGE_T, centered=(True, True, False))
          .translate(((x0 + x1) / 2, y0, top)))
wall = (cq.Workplane("XY").box(x1 - x0 + 2 * END, WALL_T, PROUD, centered=(True, True, False))
        .translate(((x0 + x1) / 2, y0 + FLANGE_W / 2 + WALL_T / 2, top)))
bracket = flange.union(wall)
for x, y in row:
    bracket = bracket.cut(cq.Workplane("XY").circle(CLEAR_D / 2).extrude(PROUD + 2)
                          .translate((x, y, top - 1)))
solid = bracket.val()
assert solid.isValid()

# fit checks against the plate
bb = solid.BoundingBox()
assert abs(bb.zmin - top) < 1e-6, f"not seated: gap {bb.zmin - top:.4f}"
assert abs(bb.zmax - top - PROUD) < 1e-6, f"stands {bb.zmax - top:.3f} proud, wanted {PROUD}"
assert solid.intersect(plate).Volume() < 1e-6, "bracket overlaps the plate"
mine = set()
for f in solid.Faces():
    if f.geomType() == "CYLINDER":
        c = BRepAdaptor_Surface(f.wrapped).Cylinder()
        if abs(c.Radius() * 2 - CLEAR_D) < 1e-6:
            mine.add((round(c.Location().X(), 6), round(c.Location().Y(), 6)))
assert mine == set(row), f"bracket holes {sorted(mine)} not on the plate holes {row}"
print("fit checks passed: seated, 15.0 proud, no overlap, both holes on the plate's hole axes", flush=True)

cq.exporters.export(bracket, str(HERE / f"{NAME}.step"))
cq.exporters.export(bracket, str(HERE / f"{NAME}.stl"))
print("DONE", flush=True)
