"""Chassis reference for the Longtail shell: the parts the shell has to clear, as plain solids.
Imported by longtail_shell_v7.py for its fit checks. Eval asset for cad-parts.

Measured off the robot 2026-10-28 (calipers) unless a line says assumed.
Axes: +x to the robot's own right, +y forward, z up. Origin on the centreline, midway between
the axles, at the base plate's top face (the shell's seat).

Run on its own to print the part list:  python chassis_ref.py
"""
import cadquery as cq

# base plate (the shell's corner bosses sit on its top face)
PLATE_W = 92.0           # x, between the wheels
PLATE_L = 223.0          # y
PLATE_T = 4.0
PLATE_Y0 = -127.0        # rear edge; front edge at PLATE_Y0 + PLATE_L = +96

# wheels: 60 mm rubber tyres on N20 hubs
WHEEL_D = 60.0
WHEEL_W = 24.0
WHEEL_X = 60.0           # wheel centre plane, each side
AXLE_Y = 50.0            # front axle +50, rear axle -50
AXLE_Z = -9.0            # axle line: N20 shafts, motors hung under the plate

# N20 gearmotors under the plate, shaft on the axle line
MOTOR_L, MOTOR_W, MOTOR_H = 34.0, 12.0, 10.0
MOTOR_X0 = 13.0          # inboard end of each motor body (x)

# electronics stack: Pi + motor board on four M2.5 standoffs
STACK_X, STACK_Y0, STACK_Y1 = 25.0, 28.0, 72.0     # standoff centres at x = +-25, y = 28 and 72
STANDOFF_D = 6.0
BOARD_W, BOARD_L, BOARD_T = 65.0, 56.0, 1.6
BOARD_Z = (12.0, 30.0)   # underside of each board

# camera behind the window in the shell's front face
CAM_W, CAM_H, CAM_T = 25.0, 24.0, 2.0
CAM_Y = 88.0             # board's back face
CAM_Z = 20.0             # board centre height
LENS_D, LENS_L = 8.0, 6.0

# rear ToF sensor on its bracket, looking out the back
TOF_W, TOF_H, TOF_T = 20.0, 14.0, 6.0
TOF_Y = -110.0           # sensor's back face (it faces -y)
TOF_Z = 6.0


def _box(x0, x1, y0, y1, z0, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def wheel(sx, sy, d=WHEEL_D, w=WHEEL_W):
    """One tyre as a solid cylinder along x (sx, sy = +-1 for the side and the axle)."""
    x0 = sx * WHEEL_X - w / 2
    return cq.Solid.makeCylinder(d / 2, w, cq.Vector(x0, sy * AXLE_Y, AXLE_Z), cq.Vector(1, 0, 0))


def parts():
    """[(name, solid)] for every chassis part the shell must not touch."""
    out = [("plate", _box(-PLATE_W / 2, PLATE_W / 2, PLATE_Y0, PLATE_Y0 + PLATE_L, -PLATE_T, 0.0))]
    for sx, side in ((1, "right"), (-1, "left")):
        for sy, axle in ((1, "front"), (-1, "rear")):
            out.append((f"wheel {axle} {side}", wheel(sx, sy)))
            x0 = MOTOR_X0 if sx > 0 else -MOTOR_X0 - MOTOR_L
            out.append((f"motor {axle} {side}", _box(x0, x0 + MOTOR_L, sy * AXLE_Y - MOTOR_W / 2,
                                                      sy * AXLE_Y + MOTOR_W / 2, AXLE_Z - MOTOR_H / 2,
                                                      AXLE_Z + MOTOR_H / 2)))
    for x in (-STACK_X, STACK_X):
        for y in (STACK_Y0, STACK_Y1):
            out.append((f"standoff {x:+.0f},{y:.0f}",
                        cq.Solid.makeCylinder(STANDOFF_D / 2, BOARD_Z[1], cq.Vector(x, y, 0))))
    yc = (STACK_Y0 + STACK_Y1) / 2
    for i, z in enumerate(BOARD_Z):
        out.append((f"board {i + 1}", _box(-BOARD_W / 2, BOARD_W / 2, yc - BOARD_L / 2, yc + BOARD_L / 2,
                                           z, z + BOARD_T)))
    out.append(("camera board", _box(-CAM_W / 2, CAM_W / 2, CAM_Y, CAM_Y + CAM_T,
                                     CAM_Z - CAM_H / 2, CAM_Z + CAM_H / 2)))
    out.append(("camera lens", cq.Solid.makeCylinder(LENS_D / 2, LENS_L, cq.Vector(0, CAM_Y + CAM_T, CAM_Z),
                                                     cq.Vector(0, 1, 0))))
    out.append(("rear ToF", _box(-TOF_W / 2, TOF_W / 2, TOF_Y - TOF_T, TOF_Y, TOF_Z, TOF_Z + TOF_H)))
    out.append(("rear ToF bracket", _box(-TOF_W / 2, TOF_W / 2, TOF_Y, TOF_Y + 3.0, 0.0, TOF_Z + TOF_H)))
    return out


if __name__ == "__main__":
    for name, s in parts():
        bb = s.BoundingBox()
        print(f"{name:20s} x {bb.xmin:7.2f}..{bb.xmax:7.2f}  y {bb.ymin:7.2f}..{bb.ymax:7.2f}  "
              f"z {bb.zmin:6.2f}..{bb.zmax:6.2f}", flush=True)
    print("DONE", flush=True)
