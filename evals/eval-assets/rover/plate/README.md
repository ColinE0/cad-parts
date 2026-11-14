# Base plate

96 x 190 mm PLA plate. The drive motors, the caster and the deck standoffs bolt to it; the IR sled
bolts under its front, the bumper on top of its front edge. Built as a chain: each step script
imports the previous step's STEP and adds one delta. `current.json` names the plate to print.

| Step | Date | Delta | Status |
|---|---|---|---|
| 1 to 8 | 2026-08-24 to 09-28 | deltas on the Onshape import | archived (`archived/WHY-ARCHIVED.md`) |
| 8c | 2026-10-02 | rebuilt from primitives; caster holes 10 mm back | printed 10-03, superseded |
| 9 | 2026-10-15 | battery strap slots | printed 10-16, superseded |
| 10 | 2026-10-29 | sled holes 6 mm forward (IR sees the line earlier); cable hole D14 | printed 10-30, bowed between the motors |
| 10c | 2026-11-08 | 4 mm thick, extra 1 mm underneath (top face unchanged) | printed 11-09, on the robot |

10b (5 mm thick) was too heavy and was dropped.

**The one to print: step 10c**, `base_plate_step10c.step` (its script writes the STL).
