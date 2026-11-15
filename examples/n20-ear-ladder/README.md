# Worked example: the N20 wheel adapter's ear ladder

A real part from a small mecanum-drive robot: printed, fitted, and frozen. `adapter_ear_ladder.py`
is here byte for byte as it was frozen, so this folder shows the whole loop: a measured problem, a
script that states a falsifiable prediction, the checks it runs, the files it exports, and what
happened on the printer.

![Rung B: the D-bore with its two corner ears](B%20bore%203.10%20%2B%20ears/adapter_ear_B_b310.png)

## The problem

An N20 gearmotor's 3 mm D-shaft drives a 48 mm mecanum wheel through a printed adapter: a D-bore
on the shaft side, a hex plug into the wheel. On 2026-08-07 a five-rung bore ladder, printed on the
same printer and profile as everything below, settled the fit: a 3.15 mm bore was "glove tight",
3.10 "did not go on", and 3.05 "had to be forced to even start".

A 0.05 mm step should not flip a fit that hard if the shaft were held by its round and flat
surfaces. A cliff that sharp points at a local interference, and a D-bore has exactly two local
features: the corners where the flat meets the arc. The shaft's corners are machined sharp; a
printer cannot make a sharp internal corner in a hole, so material bulges in exactly there.

## The prediction

The script cuts two Ø1.0 relief holes ("ears") into those corners, over the length where the
shaft's flat is engaged, and changes nothing else. Four rungs:

| Rung | Bore / flat (mm) | Without ears it was |
|---|---|---|
| A | 3.15 / 2.55 | the shipped fit, glove-tight |
| B | 3.10 / 2.50 | **did not go on**: the decisive rung |
| C | 3.05 / 2.45 | had to be forced to even start |
| D | 3.00 / 2.40 | nominal, never tried |

If B now slides on, the corner explanation is right and the bore can run tighter. If it still will
not go on, ears are a dead end. One four-part print answers it.

## The checks the script runs

- **Drift guard:** it first rebuilds the shipped 3.15 part from the same code and stops if the
  volume is not the 508.8 mm³ of the part that was actually fitted, so every rung is the proven
  part plus ears and nothing else.
- **No silent no-op:** OpenCASCADE can return its input unchanged instead of failing, so each ear
  cut must measurably remove material (`h.is_noop(h.diff(...))`).
- **Wall and size:** the wall left beside each ear must stay above 0.8 mm, and the bounding box
  must match.
- **Export gate:** every rung goes through `export_checked` (valid solid; watertight, consistently
  wound STL that agrees with its STEP) and gets a six-view render.

The script predates `GateError`, so its own checks are `assert`s. The runner starts every build
without `PYTHONOPTIMIZE`, so they always run.

## The result

Printed boss-down (bore mouth on the bed), no supports, on the same printer profile as the first
ladder, then fitted to a real motor shaft. On 2026-09-26 rung B slid on: "the ears were perfect.
they helped tremendously." The prediction held, the script was marked FROZEN, and every adapter
built since carries the ears.

## Rebuild it

From this folder, with cad-parts installed:

```powershell
& "$env:USERPROFILE\.claude\skills\cad-parts\scripts\run_watchdogged.ps1" -Script .\adapter_ear_ladder.py
```

The rebuild reproduces the September run exactly; `run_log.txt` is today's run.

| | Control (shipped 3.15) | A | B | C | D |
|---|---|---|---|---|---|
| Volume, 2026-09-18 run (mm³) | 508.8 | 500.1 | 502.3 | 504.6 | 506.7 |
| Volume, 2026-11-14 rebuild (mm³) | 508.8 | 500.1 | 502.3 | 504.6 | 506.7 |

## Files

| Path | What |
|---|---|
| `adapter_ear_ladder.py` | the frozen script (STATUS line at the top) |
| `A bore 3.15 + ears\` to `D bore 3.00 + ears\` | each rung's STEP, STL and six-view render |
| `run_log.txt` | the rebuild's run log, local paths removed |

This adapter is one part of the robot's wheel chain; the rest (the printed hub cheeks and the
final wheel) is summarised in the main README's [physical record](../../README.md#physical-record).
Those parts are built on the wheel vendor's CAD model, so their files are not published.
