"""Sled bridge: a 4 mm deck on two end walls over a 3 mm base plate, with a centre post under the
middle of the deck to stiffen its 70 mm span. Eval asset for cad-parts.

STATUS: trial, unprinted.
Axes: x runs end wall to end wall, y front to back, z up. Prints upright, base plate on the bed.

Run:  python sled_bridge.py
Outputs sled_bridge.step and sled_bridge.stl beside this script.
"""
from pathlib import Path

import cadquery as cq

OUT = Path(__file__).resolve().parent
NAME = "sled_bridge"

L = 80.0        # x, outside of one end wall to the other
W = 40.0        # y
H = 32.0        # z, bed to the top of the deck
BASE_T = 3.0    # base plate
WALL_T = 5.0    # end walls
DECK_T = 4.0    # deck
POST = 6.0      # centre post, square, base plate to deck

assert POST < L - 2 * WALL_T, "post wider than the gap between the walls"

base = cq.Workplane("XY").box(L, W, BASE_T, centered=(True, True, False))
wall = cq.Workplane("XY").box(WALL_T, W, H, centered=(True, True, False))
walls = wall.translate((-(L - WALL_T) / 2, 0, 0)).union(wall.translate(((L - WALL_T) / 2, 0, 0)))
deck = cq.Workplane("XY").box(L, W, DECK_T, centered=(True, True, False)).translate((0, 0, H - DECK_T))
post = (cq.Workplane("XY").box(POST, POST, H - DECK_T - BASE_T, centered=(True, True, False))
        .translate((0, 0, BASE_T)))
part = base.union(walls).union(deck).union(post)

solid = part.val()
assert solid.isValid()
bb = solid.BoundingBox()
print(f"bbox {bb.xlen:.2f} x {bb.ylen:.2f} x {bb.zlen:.2f} mm, volume {solid.Volume():.2f} mm3", flush=True)
assert abs(bb.xlen - L) < 1e-6 and abs(bb.ylen - W) < 1e-6 and abs(bb.zlen - H) < 1e-6

cq.exporters.export(part, str(OUT / f"{NAME}.step"))
cq.exporters.export(part, str(OUT / f"{NAME}.stl"))
print("DONE", flush=True)
