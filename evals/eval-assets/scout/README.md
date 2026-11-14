# Scout

Four-wheel-drive indoor scout with a charging dock. One folder per printed part; each folder's
README names the file to print.

| Folder | Part |
|---|---|
| `shell/` | top shell: arches over the tyres, dock slot, roof hatch, camera window |
| `lid/` | hatch lid: drops into the shell's roof hatch |
| `bumper/` | front bumper: bolts up under the plate's front edge |
| `camera/` | camera mount: on the plate, behind the shell's window |

`scout_refs.py` holds what the part scripts share: the axes, the chassis parts (plate, tyres,
motors, dock bar, electronics stack) and the roof hatch.

Axes: +x to the robot's own right, +y forward, z up; origin on the centreline, midway between the
axles, at the base plate's top face.

Scripts run with the CadQuery venv, through the cad-parts runner.
