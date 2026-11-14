# Rover

Two-wheel-drive line follower with a rear ball caster. One folder per part; each folder's README
names the file to print.

| Folder | Part |
|---|---|
| `plate/` | base plate: a chain of step scripts, one delta each |
| `sled/` | IR sled: holds the line board under the front of the plate |
| `bumper/` | front bumper: bolts down onto the plate's front edge |

`rover_refs.py` holds what the part scripts share: the axes, the drive train, the IR board, and
the base plate the chassis parts bolt to (`load_plate()`, `holes()`).

Axes: +x to the robot's own right, +y forward, z up; origin on the centreline, on the drive axle
line, at the plate's top face.

Scripts run with the CadQuery venv, through the cad-parts runner.
