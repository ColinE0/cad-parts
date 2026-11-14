"""Shared references for the Rover's part scripts: axes, the drive train, the IR boards, and the
base plate the chassis parts bolt to. Part scripts import this module; do not copy numbers out of
it. Eval asset for cad-parts.

Axes: +x to the robot's own right, +y forward, z up. Origin on the centreline, on the drive axle
line (y = 0), at the base plate's top face (z = 0).
Measured off the robot 2026-09-30 (calipers) unless a line says assumed.
"""
from pathlib import Path

import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface

ROOT = Path(__file__).resolve().parent
PLATE_DIR = ROOT / "plate"
PLATE_STEP = PLATE_DIR / "base_plate_step8c.step"     # the base plate the chassis parts bolt to

# plate holes the dependents bolt through (diameters as drilled in the plate)
SLED_HOLE_D = 3.4        # IR sled, under the front of the plate
BUMPER_HOLE_D = 3.2      # front bumper, on top of the front edge

# drive train: two N20 gearmotors under the plate, 66 mm wheels, rear ball caster
WHEEL_D, WHEEL_W = 66.0, 26.0
WHEEL_X = 62.0           # wheel centre plane, each side
AXLE_Z = -8.0            # N20 shaft line under the plate
FLOOR_Z = AXLE_Z - WHEEL_D / 2   # the floor the robot drives on, -41
CASTER_Y = -88.0         # caster centre (y)
CASTER_D, CASTER_H = 24.0, 37.0  # caster housing, floor up to its mounting face

# IR line boards (two, side by side on the sled's lip)
IR_BOARD_W, IR_BOARD_L, IR_BOARD_T = 40.0, 14.0, 1.6
IR_EMITTER_H = 3.2       # emitter/receiver pair below the board


def load_plate():
    """The base plate as a cadquery Shape, in robot axes."""
    return cq.importers.importStep(str(PLATE_STEP)).val()


def holes(shape, max_d=8.0):
    """[(x, y, diameter)] of the round holes through `shape` whose axis runs along z, sorted.
    Corner fillets are cylinder faces too; max_d keeps them out (the plate's are R10)."""
    out = set()
    for f in shape.Faces():
        if f.geomType() != "CYLINDER":
            continue
        c = BRepAdaptor_Surface(f.wrapped).Cylinder()
        if abs(abs(c.Axis().Direction().Z()) - 1) > 1e-9 or 2 * c.Radius() > max_d:
            continue
        out.add((round(c.Location().X(), 4), round(c.Location().Y(), 4), round(2 * c.Radius(), 4)))
    return sorted(out)


def wheels():
    """[(name, solid)]: both drive wheels and the caster housing, for clearance checks."""
    out = []
    for sx, side in ((1, "right"), (-1, "left")):
        out.append((f"wheel {side}", cq.Solid.makeCylinder(
            WHEEL_D / 2, WHEEL_W, cq.Vector(sx * WHEEL_X - WHEEL_W / 2, 0, AXLE_Z), cq.Vector(1, 0, 0))))
    out.append(("caster", cq.Solid.makeCylinder(CASTER_D / 2, CASTER_H, cq.Vector(0, CASTER_Y, FLOOR_Z))))
    return out
