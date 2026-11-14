"""Builds the binary inputs for evals 7 and 9 into ../eval-assets. Run it through the runner with the
eval venv (it imports cq_helpers from this repo's cad-parts/venv-modules):

    & ..\\..\\cad-parts\\scripts\\run_watchdogged.ps1 -Script make_assets.py -Python <venv python>

Eval 7: puck.step, a filleted, holed puck (D30 x 10, D8 bore, 4 x D3.2 on a 22 mm circle, R1.5 on
the outer top and bottom edges): the 2026-10-05 stand-in from references/gotchas.md, as an
imported STEP of analytic faces.

Eval 9: plate-chain-moved/, the eval 4 plate chain one step later. plate_step1.step is eval 4's
file byte for byte; plate_step2.step is the newer plate (66 x 40 x 5, top face 1 mm higher, holes
moved out to x = +-28), and current.json names step 2. plate_bracket.py (written by hand) still
imports step 1 by filename.

The sled bridge script for eval 8 is written by hand too (eval-assets/sled_bridge.py).
"""
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "cad-parts" / "venv-modules"))

import cadquery as cq  # noqa: E402
import cq_helpers as h  # noqa: E402

ASSETS = HERE.parent / "eval-assets"

# eval 7: the puck
PUCK_D, PUCK_H, BORE_D = 30.0, 10.0, 8.0
HOLE_D, HOLE_PCD, FILLET_R = 3.2, 22.0, 1.5
puck = (cq.Workplane("XY").circle(PUCK_D / 2).extrude(PUCK_H)
        .edges(">Z or <Z").fillet(FILLET_R)
        .faces(">Z").workplane().hole(BORE_D)
        .faces(">Z").workplane().polarArray(HOLE_PCD / 2, 45, 360, 4).hole(HOLE_D))
h.export_checked(puck, str(ASSETS / "puck"), stl=False)
d = h.describe(cq.importers.importStep(str(ASSETS / "puck.step")).val())
print("puck.step:", d, flush=True)
assert d["faces"] == 10 and d["bbox_mm"] == [30.0, 30.0, 10.0], d

# eval 9: the plate chain, moved on to step 2
chain = ASSETS / "plate-chain-moved"
chain.mkdir(exist_ok=True)
shutil.copyfile(ASSETS / "plate-chain" / "plate_step1.step", chain / "plate_step1.step")
P2_L, P2_W, P2_T, P2_Z0 = 66.0, 40.0, 5.0, -2.0      # step 1 was 60 x 40 x 4 from z -2
P2_HOLE_X, P2_HOLE_Y, P2_HOLE_D = 28.0, 15.0, 3.2     # step 1 had x = +-25
plate2 = (cq.Workplane("XY").box(P2_L, P2_W, P2_T, centered=(True, True, False)).translate((0, 0, P2_Z0))
          .faces(">Z").workplane()
          .pushPoints([(sx * P2_HOLE_X, sy * P2_HOLE_Y) for sx in (-1, 1) for sy in (-1, 1)])
          .hole(P2_HOLE_D))
h.export_checked(plate2, str(chain / "plate_step2"), stl=False)
h.set_current(chain, "plate_step2.step",
              note="step2 is the plate to print: 1 mm thicker, 6 mm wider, bolt holes moved out to x = +-28 "
                   "for the battery tray")
print("step 1:", h.describe(cq.importers.importStep(str(chain / "plate_step1.step")).val()), flush=True)
print("step 2:", h.describe(cq.importers.importStep(str(chain / "plate_step2.step")).val()), flush=True)
print("DONE", flush=True)
