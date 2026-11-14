"""Shared references for the Scout's part scripts: axes, the chassis parts the printed parts must
clear, and the roof hatch the shell and the lid share. Eval asset for cad-parts.

Axes: +x to the robot's own right, +y forward, z up. Origin on the centreline, midway between the
axles, at the base plate's top face.
Measured off the robot 2026-10-21 (calipers) unless a line says assumed.
"""
import cadquery as cq

# base plate
PLATE_W, PLATE_L, PLATE_T = 84.0, 176.0, 3.0
PLATE_Y0 = -88.0                 # rear edge; front edge at +88

# four-wheel drive: N20 gearmotors under the plate, rubber tyres
WHEEL_D, WHEEL_W = 52.0, 20.0
WHEEL_X = 52.0                   # wheel centre plane, each side
AXLE_Y = 46.0                    # front axle +46, rear axle -46
AXLE_Z = -8.0                    # shaft line: N20s hung under the plate
MOTOR_L, MOTOR_W, MOTOR_H, MOTOR_X0 = 30.0, 12.0, 10.0, 11.0

# charging dock: its contact bar slides in under the shell across x, on the plate
DOCK_W, DOCK_H = 28.0, 8.0       # y, z

# electronics stack on four standoffs, behind the front axle
STACK_X, STACK_Y = (-22.0, 22.0), (-34.0, 22.0)
STANDOFF_D, STACK_TOP = 6.0, 26.0
BOARD_W, BOARD_L, BOARD_T = 56.0, 64.0, 1.6

# roof hatch: the shell cuts it, the lid drops into it
ROOF_Z = 48.0                    # shell roof top
RIM_H = 2.0                      # raised rim round the hatch
HATCH_W, HATCH_L, HATCH_Y = 56.0, 64.0, -6.0


def _box(x0, x1, y0, y1, z0, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def wheel(sx, sy, d=None, w=None):
    """One tyre as a solid cylinder along x (sx, sy = +-1: side and axle)."""
    d = WHEEL_D if d is None else d
    w = WHEEL_W if w is None else w
    return cq.Solid.makeCylinder(d / 2, w, cq.Vector(sx * WHEEL_X - w / 2, sy * AXLE_Y, AXLE_Z), cq.Vector(1, 0, 0))


def parts():
    """[(name, solid)] for every chassis part the shell must not touch."""
    out = [("plate", _box(-PLATE_W / 2, PLATE_W / 2, PLATE_Y0, PLATE_Y0 + PLATE_L, -PLATE_T, 0.0))]
    for sx, side in ((1, "right"), (-1, "left")):
        for sy, axle in ((1, "front"), (-1, "rear")):
            out.append((f"wheel {axle} {side}", wheel(sx, sy)))
            x0 = MOTOR_X0 if sx > 0 else -MOTOR_X0 - MOTOR_L
            out.append((f"motor {axle} {side}", _box(x0, x0 + MOTOR_L, sy * AXLE_Y - MOTOR_W / 2,
                                                      sy * AXLE_Y + MOTOR_W / 2, -PLATE_T - MOTOR_H, -PLATE_T)))
    out.append(("dock bar", _box(-150.0, 150.0, -DOCK_W / 2, DOCK_W / 2, 0.0, DOCK_H)))
    for x in STACK_X:
        for y in STACK_Y:
            out.append((f"standoff {x:+.0f},{y:+.0f}", cq.Solid.makeCylinder(STANDOFF_D / 2, STACK_TOP, cq.Vector(x, y, 0))))
    yc = sum(STACK_Y) / 2
    out.append(("board", _box(-BOARD_W / 2, BOARD_W / 2, yc - BOARD_L / 2, yc + BOARD_L / 2, STACK_TOP, STACK_TOP + BOARD_T)))
    return out
