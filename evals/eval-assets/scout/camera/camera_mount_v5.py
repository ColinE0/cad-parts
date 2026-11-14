"""Scout camera mount, v5: holds the camera board behind the window in the shell's front face,
tilted down to see the floor ahead. A flange bolts to the plate's top face; the board screws to
the upright's tilted front face (4 M2 self-tappers on the board's 21 x 12.5 pattern).
Eval asset for cad-parts.

v5 delta (from v4): upright 4 mm taller so the lens lines up with the v3 shell's window.

STATUS: printed 2026-11-06, fitted, FROZEN.
Axes: scout_refs.py, modelled where it sits on the robot.
Prints on its side: the robot's right-hand side face (+x) on the bed.

Run:  python camera_mount_v5.py
Writes camera_mount_v5.step and stl/camera_mount_v5.stl beside this script.
"""
import math
import sys
from pathlib import Path

import cadquery as cq

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import scout_refs as R  # noqa: E402

NAME = "camera_mount_v5"

TILT_DEG = 10.0                              # board faces forward and this far down
FLANGE_W, FLANGE_Y0, FLANGE_Y1, FLANGE_T = 30.0, 64.0, 78.0, 3.0
BOLT_X, BOLT_Y, CLEAR_D = 10.0, 69.0, 3.3    # two M3 through the flange into the plate
UPRIGHT_W, UPRIGHT_Y0 = 26.0, 66.0           # upright width (x), back face (y)
FACE_Y, FACE_Z = 80.0, 17.0                  # point on the tilted face: the board's centre
FACE_Z1 = 31.0                               # top of the upright
BOARD_HOLES = (21.0, 12.5)                   # camera board's M2 pattern (x, along the face)
PILOT_D, PILOT_DEPTH = 1.7, 6.0

t = math.radians(TILT_DEG)
n = cq.Vector(0, math.cos(t), -math.sin(t))          # face normal, out of the face
up = cq.Vector(0, math.sin(t), math.cos(t))          # up the face


def face_y(z):
    return FACE_Y + (z - FACE_Z) * math.tan(t)


flange = cq.Workplane("XY").add(cq.Solid.makeBox(FLANGE_W, FLANGE_Y1 - FLANGE_Y0, FLANGE_T,
                                                 cq.Vector(-FLANGE_W / 2, FLANGE_Y0, 0)))
z0 = FLANGE_T - 0.5
upright = (cq.Workplane("YZ", origin=(-UPRIGHT_W / 2, 0, 0))
           .polyline([(UPRIGHT_Y0, z0), (face_y(z0), z0), (face_y(FACE_Z1), FACE_Z1), (UPRIGHT_Y0, FACE_Z1)])
           .close().extrude(UPRIGHT_W))
mount = flange.union(upright)
centre = cq.Vector(0, FACE_Y, FACE_Z)
for sx in (1, -1):
    for su in (1, -1):
        p = centre + cq.Vector(sx * BOARD_HOLES[0] / 2, 0, 0) + up * (su * BOARD_HOLES[1] / 2)
        mount = mount.cut(cq.Workplane("XY").add(cq.Solid.makeCylinder(PILOT_D / 2, PILOT_DEPTH + 1, p + n * 1.0, -n)))
for sx in (1, -1):
    mount = mount.cut(cq.Workplane("XY").add(cq.Solid.makeCylinder(CLEAR_D / 2, FLANGE_T + 2,
                                                                   cq.Vector(sx * BOLT_X, BOLT_Y, -1))))

solid = mount.val()
assert solid.isValid() and len(mount.solids().vals()) == 1
bb = solid.BoundingBox()
print(f"bbox {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f} mm, volume {solid.Volume():.2f} mm3", flush=True)

# fit checks: flange down on the plate, nothing into it; the board face really is at TILT_DEG
plate = dict(R.parts())["plate"]
assert abs(bb.zmin) < 1e-6 and solid.intersect(plate).Volume() < 1e-6, "mount not seated on the plate"
faces = [f for f in solid.Faces() if f.geomType() == "PLANE" and abs(f.normalAt().x) < 1e-6
         and f.normalAt().y > 0.5 and f.normalAt().z < -1e-3]
board_face = max(faces, key=lambda f: f.Area())       # the pilot holes' flat bottoms share its normal
assert board_face.Area() > 0.8 * UPRIGHT_W * (FACE_Z1 - z0), "tilted board face missing or cut up"
nm = board_face.normalAt()
got = math.degrees(math.atan2(-nm.z, nm.y))
assert abs(got - TILT_DEG) < 1e-6, f"board face tilted {got:.3f} deg, wanted {TILT_DEG}"
print(f"fit checks passed: seated on the plate, board face at {got:.2f} deg down", flush=True)

(HERE / "stl").mkdir(exist_ok=True)
cq.exporters.export(mount, str(HERE / f"{NAME}.step"))
cq.exporters.export(mount, str(HERE / "stl" / f"{NAME}.stl"))
print("DONE", flush=True)
