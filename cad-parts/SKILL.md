---
name: cad-parts
description: Author physical 3D parts as local .stl/.step files with CadQuery, run as one-shot RAM-watchdogged subprocesses against C:\cadquery-venv. Use whenever the user wants to design, model, create, resize, trim, or remix a printable part (an adapter, standoff, spacer, bracket, mount, enclosure, keycap, robot or chassis piece), asks for an STL or STEP file, wants a dimension changed on an existing part script, wants a part rendered, measured, or verified, wants a broken STL repaired, or wants a part re-checked against a parent part that changed, even if they never say "CadQuery" or "CAD". NOT for PCB design or slicer/print settings.
---

Copyright 2026 Colin Ezra Wilder. Licensed under the Apache License, Version 2.0
(the LICENSE and NOTICE files that come with this skill).

# CAD parts via CadQuery subprocess

Local, scriptable CAD: a Python script builds the solid, a watchdogged subprocess
runs it, `cq_helpers` gates the export, a 6-view PNG proves the shape. The user
prints the results on FDM printers, so every STL that leaves here must slice cleanly.

## Non-negotiables

1. **One-shot subprocess only.** On 2026-07-14 a long-lived CAD server
   process OOM-crashed the entire machine as imported models accumulated across
   calls (a 2026-11-14 replay cleared the non-uniform scale first blamed; see
   gotchas). A crashed subprocess loses one run; a crashed in-process op takes
   the box down. Run every build through `scripts/run_watchdogged.ps1`, and
   every other venv script too (drawing probes, mesh checks), CadQuery or not.
   When `hooks/require_runner.py` is registered as a Claude Code hook (README),
   a direct call to the venv's Python is refused with the runner command to use
   instead: that refusal is the rule working, not an error to route around.
2. **Never edit a proven part file.** A script whose print has been tested and
   works is frozen. Variants get a NEW file (e.g. `adapter_hex_trim.py` next to
   `adapter_hex.py`) with a docstring naming exactly what changed and why. Every
   script carries a `STATUS:` line (Script conventions) so "proven" is written
   down, not remembered.
3. **Every export goes through `cq_helpers.export_checked`.** BRep `isValid()`
   alone does not guarantee a clean mesh; slicers reject non-watertight STLs
   that pass validity checks. This gate has already caught a shipped bad part.
4. **Every part that will be printed gets an island check in its PRINT
   orientation.** `h.islands(solid, up="+z")` (or the planned up axis) finds
   material that starts above the bed and only joins the part layers later,
   so it stands on supports the whole way up. A HIGH island is a design
   problem to fix or put to the user before any print plan, never "supports
   will handle it". On 2026-10-09 a robot shell's wheel-gap pillar was one
   (36.8 mm tall on tree supports, 6.52 thin) and snapped off partway
   through a 22 h three-colour print, after every fit gate had passed. Fit
   gates ask "does it fit"; this one asks "can it be built bottom-up".

## Workflow

0. **Confirm what the prompt leaves open.** A complete spec ("12 mm tall, 9 OD,
   4.3 hole") needs no gate. When a load-bearing choice is open (which holes,
   what "15 mm proud" is measured from, what mounts on it, which hardware,
   which folder), state your reading as a short proposal and ask the user
   before building. Reference images always get this gate (see below).
1. **Write the script.** Deliverable parts: the script lives next to its outputs
   in the part's folder (the script IS the record of the part; see "Where parts
   live"). Probes and experiments: a scratch folder.
2. **Run it:**
   ```powershell
   & "$env:USERPROFILE\.claude\skills\cad-parts\scripts\run_watchdogged.ps1" -Script "C:\path\to\part.py" -Tail 40
   ```
   Defaults: 300 s timeout, 4 GB cap, 500 ms poll, interpreter
   `C:\cadquery-venv\Scripts\python.exe` (override with `-Python <path>` or the
   `CADPARTS_PYTHON` environment variable). The cap is on the committed
   memory of the whole process tree, kernel-enforced through a Windows job
   object: an allocation past it is refused (the script sees `MemoryError` or
   an OCCT allocation failure) and the runner kills the tree, exit 137.
   Importing cadquery alone commits about 0.7 GB, so never cap below ~1 GB.
   Raise limits only deliberately for a known-heavy job, never as a first
   response to a kill; a watchdog kill usually means a geometry mistake (see
   gotchas), not a small cap.
   `-Tail N` prints only the last N stdout lines; the full log is always in
   `<script>.out.txt` beside the script. Use it on long-logging scripts so the
   whole log does not land in context. The summary line reports wall time:
   choose `-TimeoutSec` from that, not by guess.
   Through a PowerShell tool, set the tool's own timeout above `-TimeoutSec`.
   If the tool kills the runner first, the job object takes the build down with
   it: the run is lost, never orphaned.
3. **Read the output.** The runner prints the script's stdout, any stderr, wall
   time, and the tree's peak committed memory. Require the `DONE` sentinel; a
   run without it did not finish. Exit 137 = watchdog kill (the last line says
   timeout or cap); 3 = the watchdog could not arm (or the interpreter is
   missing), so the script never ran. `<script>.out.txt` is the build's run log
   (READMEs cite it); `<script>.err.txt` exists only when stderr had content.
   On a cap kill, triage before touching any limit (gotchas: "Triage a cap kill").
4. **Verify before reporting.** Read the `render6` PNG and check the silhouette
   against intent. Report dimensions from the script's printed bbox/volume, not
   from memory. Check each feature by MEASURING the built solid (`describe`,
   face bboxes, a slab intersected through the wall); an assert that compares
   an input constant against itself proves nothing. Then run `h.islands` in
   the orientation the part will print (non-negotiable 4) and report what it
   flags with the part.
5. **Record.** Update the folder README (which file to print), set the STATUS
   line, and write down anything learned that the next session needs (see
   "Recording").

## Where parts live and what a part folder holds

Parts root: **ASK** (if this still says ASK, ask the user where parts should
live, e.g. `C:\Users\<name>\Documents\cad-parts`, and offer to write it here).
Every part gets its own folder under that root; group related parts in
subfolders (a robot's chassis parts together, one-off prints together). If a
part's home is unclear, ask; do not guess.

A part folder holds:

- The script(s), STEPs and renders at the top level; **every STL in an `stl/`
  subfolder** (export with `stl_dir="stl"`). In a chain folder (see "Chain
  edits") the top level holds ONE live version of the part: if there is an STL
  in `stl/` for the top-level part, it is the one to print. A broken STL
  someone hands over stays at the top level, never in `stl/`, since `stl/`
  means printable.
- `README.md`: what the part is, the lineage ("in use: v12, newest: v16 trial"),
  and an explicit "the one to print" line. Nothing moves to `archived/`
  without the user's OK. No README yet: write one. Sibling sizes rather than
  versions (an 11 mm and a 14 mm standoff) get one print line each.
- `archived/`: superseded versions, one folder per version or chain step, each
  with its script, STEP, STL, renders and run log together, and
  `WHY-ARCHIVED.md` at the archive root. Archived chain steps do not re-run in
  place (their source paths assume the old layout); copy one back to the top
  level first.
- `DEAD-*.md` markers for features that must never come back (e.g.
  `CRUSH-RIBS-DEAD-DO-NOT-REBUILD.md`: crush ribs that destroyed two motors).
  Read any DEAD file in the folder before touching the part.
- A print plan, if one is written, tied to one STL name; mark it stale when
  the part moves on.
- `<script>.out.txt`, the build's run log.
- `current.json` in chain folders (next sections).

## Script conventions

- Module docstring: what the part is, why it exists, how to run it, and a
  `STATUS:` line (make it a raw docstring, `r"""`, when it holds Windows paths:
  CPython 3.14 warns on `\c`, `\s` escapes): `STATUS: printed 2026-09-08, fitted, FROZEN` or
  `STATUS: trial, unprinted`. FROZEN is what non-negotiable 2 means by proven;
  update the line when a print result comes back.
- The docstring holds THIS version's delta and its reasoning. Lineage and which
  file to print belong in the README. Do not paste the previous version's notes
  forward (one script that did reached 50 KB).
- **Version numbers step by tenths**: each new build of a versioned part line
  is +0.1, `v22` -> `v22.1` ... `v22.9` -> `v23`, never skipping ahead unless
  the user says so. Files write the dot as an underscore
  (`chassis_v22_1.py`, `.step`, `stl/..._v22_1.stl`) because later scripts
  import earlier versions as modules (`import chassis_v12 as V12`) and a dotted
  module name cannot be imported; docstrings and READMEs say "v22.1". Existing
  files keep their numbers. Chain steps (`step8`, `step11e`) keep their own
  scheme, and any version stamp engraved on a part stays the user's own count.
- ALL dimensions as named constants at the top, in mm, one place to edit.
- `import cq_helpers as h` (installed in the venv's site-packages).
- **Say WHICH hand** whenever you write left or right: the robot's or part's
  own left (as if you were it, facing forward) or the viewer's left looking at
  its front. They are opposite; a bare "left" in a docstring, README or message
  is a defect. Write the axis convention (which way is front, +x, up) at the top
  of any multi-part project and keep it.
- Assert `solid.isValid()` and assert the bounding box matches the intended
  dims; guard formulas as asserts too (e.g. bore depth must exceed shaft
  protrusion), so a bad param edit fails loudly instead of printing scrap.
- Mating hardware is modeled as solids and checked with `h.interference`. Take
  the dimensions from a datasheet or a caliper and mark each constant's comment
  measured or assumed, with where the number came from. Default fastener values
  when nothing better is known: M3 socket head 5.5 x 3.0, M3 clearance D3.30,
  M2 self-tap pilot into PLA D1.7 to 1.8. Other standard fasteners: ISO 261
  thread and ISO 273 clearance, marked assumed.
- `print(..., flush=True)` for progress; end with `print("DONE", flush=True)`.
- Export: `h.export_checked(solid, str(OUT / "part_name"), stl_dir="stl")` then
  `h.render6(solid, str(OUT / "part_name.png"))`.
- One part per exported file; parts are printed individually.

## Chain edits on an imported STEP

Many parts are a delta on an imported parent STEP (one base plate reached
step 10c through nine such deltas). Rules:

- Name steps `step<N>`, with a suffix letter for a branch (`step7c`) or a rebase
  (`step5r`); the docstring's SRC line names the parent file. A rebase gets a
  WHY note in the folder.
- The chain folder carries `current.json` naming the live parent. Write it with
  `h.set_current(folder, "part.step", note="2026-09-22: ...")` when the user
  names the part to print, or from the step script right after its
  `export_checked`. The README's "the one to print" line and `current.json`
  must agree.
- Dependents import the parent with
  `plate = h.import_current(PLATE_DIR, pin="base_plate_step10c")`,
  never by a hard-coded filename. When the chain moves, the pinned build FAILS
  naming both parts; re-run every fit check against the new parent, then move
  the pin. The fingerprint check also fails if the STEP was replaced without
  `set_current`. (Why: dependents once stopped running when their parent STEP
  vanished, and one passed every check pinned to an old parent while a newer
  one was the part to print.)
- Prove the delta: `h.diff` before and after, and assert everything outside
  the edit box is unchanged.
- A NEW dependent part (a bracket bolted to a plate) asserts at least:
  seated (zero gap to the mating face, no overlap), its hole axes on the
  parent's, shank clearance in both holes, head and tool access clear (a
  hex-key column over each head), and any parent feature it must not block
  still free. Read the parent's holes from its B-rep, filtering cylinder faces
  by axis direction, since a fillet is a cylinder face too.
- Parameter-only variant of a script (the 14 mm copy of an 11 mm standoff):
  prove "nothing else changed" with a text diff of the two scripts (only the
  docstring, NAME and the parameter differ) plus `describe()` against the
  analytic volume. No geometry-diff probe needed.
- A non-uniform scale turns every face of an imported B-rep into a B-spline
  (gotchas): offsets can fail after it. Rebuild, or scale the mesh.

## cq_helpers API (venv site-packages)

- `export_checked(shape, basepath, stl=True, step=True, stl_dir=None, mesh=None, agree_tol=0.015)`:
  accepts Workplane or Shape; requires `isValid()`; writes `.step`/`.stl` (the STL into
  `<dir of basepath>/<stl_dir>/` when `stl_dir` is set, always `"stl"` here); trimesh watertight +
  winding gate on the STL with auto-repair (merge_vertices digits 5 then 4,
  fill_holes, fix_normals, accepted only if volume drift < 0.5%); then the STL
  must agree with the STEP read back from disk (or with shape when `step=False`):
  bounding box within max(0.05 mm, 0.5 % of the part's largest size) per side,
  volume within `agree_tol`. Returns the trimesh mesh. Every failed check raises
  `h.GateError` (an AssertionError subclass, raised explicitly so `python -O`
  cannot skip it), which stops the run. Prints one `export ok:` line per file
  written, full path with extension, and one `export check:` line with the
  agreement numbers.
  The auto-repair closes hairline tessellation cracks on a valid B-rep; it
  will NOT close a missing face (see "Repairing a mesh the user hands over").
  The STL is meshed on a fresh copy (shape stays unmeshed), so a mesh pinned
  on shape first is dropped: pin it with `mesh=(deflection, angular)` (mm
  absolute, rad; vendor parts with sliver faces needed `(0.05, 0.2)`, gotchas).
- `render6(shape, png_path, color="#b25563", tol=0.3)`: 6 canonical shaded
  views (front/back/left/right/top/front-3/4) to one PNG. A depth-buffered VTK
  offscreen render (matplotlib's painter sort faked see-through on assemblies,
  gotchas), parallel projection, each view framed on the part; a Workplane
  renders every Shape on its stack; `tol` is the tessellation's linear
  deflection in mm (0.6 for big assemblies).
- `render_compare(shape, ref_image_path, png_path)`: reference image beside
  3 shaded views in one PNG, same renderer. Mandatory gate for
  reference-derived parts (see below); read the PNG, don't just generate it.
- `render_views(items, png_path, views, title=None, size=(800, 640),
  cols=None, legend=None, tol=0.3, frame=None, bg="white")`: the same
  renderer for multi-colour assemblies. `items` is `[(shape, colour)]` (or
  `(shape, colour, tol)`); a shape may be a pre-tessellated (N, 3, 3) array
  so a part drawn in many renders is tessellated once. `views` is
  `[(label, elev, azim)]` in matplotlib's angles; `size` is pixels per view;
  `legend` is `[(colour, label)]`; `frame` is an (xmin, xmax, ymin, ymax,
  zmin, zmax) box to frame a close-up on. One unlabelled view writes exactly
  `size`. Use it instead of hand-rolling a matplotlib `Poly3DCollection`
  (gotchas: painter sort).
- `describe(shape)`: geometry truth block, a dict with exactly these keys:
  `solids`, `faces`, `edges`, `vertices`, `volume_mm3`, `area_mm2`, `bbox_mm`
  (size [x, y, z]), `bbox_min`, `bbox_max`, `center_mass` (all mm). Print it
  instead of hand-rolling bbox/volume reports.
- `diff(before, after)`: delta between two `describe()` blocks (volume, area,
  bbox, center-of-mass, topology counts). Use around a feature to prove its
  effect: did the cut remove volume, did the fillet add faces.
- `is_noop(diff_result)`: True when a diff is all-zero. OCCT sometimes returns
  the input UNCHANGED instead of raising (e.g. a shell it can't offset); after
  any op that must change geometry, `assert not h.is_noop(h.diff(g0, g1))`.
- `interference(a, b, clearance=False)`: boolean-common overlap between two
  solids: `intersects`, `volume_mm3`, overlap bbox. With `clearance=True` and
  disjoint solids, adds `clearance_mm` (vertex-sampled approximation, treat as
  an estimate). This is the "measure the interference numerically before
  redesigning" tool: model the mating hardware (screw-head sweep, wheel swing)
  as a solid and intersect it against the part. Never hand it a compound;
  check each solid (`shape.Solids()`). `clearance_mm` is the GLOBAL minimum
  over both solids: a probe parked just above a seat reports that offset, not
  the side gap you meant. To measure one gap (head vs upright), cut or
  intersect the target down to that feature first.
- `hints_for_error(msg)`: maps cryptic OCCT errors (BRep_API: command not
  done, Standard_ConstructionError, ...) to actionable fixes. Importing
  cq_helpers installs an excepthook, so an uncaught crash in a one-shot script
  automatically prints `HINT:` lines after the traceback; read them before
  re-deriving what went wrong.
- Chain pointer: `set_current(folder, step_file, note="")`,
  `read_current(folder)`, `import_current(folder, pin=None)`,
  `fingerprint(shape)`, `fingerprint_matches(a, b)`. See "Chain edits".
- Mesh path: `dedupe_points(pts, eps=1e-3)` for DXF loops; `snap_float32(mesh)`
  rebuilds a trimesh through manifold3d at float32 and asserts it clean and
  float32-exact; `mesh_to_solid(mesh, sew_tol=1e-5)` sews a clean mesh into an
  OCCT solid so a mesh-only part can pass `export_checked` (use `step=False`).
- Letters: `glyph(ch, size, depth, font, font_path)` returns one character
  centred on its ink box; `fit_text_size(chars, win_w, win_h, ...)` solves ONE
  size that fits every character in a window. Name `font_path` explicitly;
  assert the returned cap height against a minimum so a silently substituted
  font fails instead of printing small.
- Printability: `islands(part, up="+z", layer=0.2, report=True)` takes a Shape,
  Workplane, trimesh mesh or STL path, slices it every layer in the print
  orientation and joins regions layer to layer by overlap. It returns (and
  prints, one line each) every island: `z0`/`z1` above the bed (where it
  starts, where it first joins grounded material), `height`, thin side
  `min_width_mm`, `slender`, `risk` (HIGH at slender >= 3 or 15 mm tall, watch
  at 1.5 or 5 mm) and model `at_xyz`. Bosses hanging from a roof show up as
  small "watch" islands; HIGH ones are the snap risk. About 5 s on a 64 cm3
  shell. It does not flag a grounded but slender fin. It meshes a copy (the
  caller's solid stays unmeshed and valid) and closes hairline seam cracks with
  export_checked's merge before slicing (gotchas: "A HIGH island that is only
  a mesh crack").
- `scripts/test_cq_helpers.py` exercises all of the above (plain asserts, ends
  with DONE). Run it through the runner after ANY edit to `cq_helpers.py`.

## Repairing a mesh the user hands over

"The slicer calls this STL non-manifold" is a mesh job, not a build:

1. Diagnose with numbers from a probe run through the runner: triangle count,
   open (boundary) edges and the loops they form, edges shared by more than two
   faces, duplicate or degenerate triangles, near-coincident vertices, and
   winding (trimesh `is_watertight`, `is_winding_consistent`, plus an edge
   census from `faces_unique_edges` / `edges_unique` counts). Name exactly what
   is wrong before fixing it.
2. Fix the cause: patch the missing triangles (wound outward), or rebuild the
   part parametrically when it is simple and the mesh is junk.
3. `h.snap_float32(mesh)`, then `h.mesh_to_solid(mesh)` (it refuses a mesh
   that still has free edges, which is the check you want), then
   `h.export_checked(solid, base, step=False, stl_dir="stl")`.
4. Re-read the written STL and report watertight, open edges, volume and bbox
   against the original. The original stays untouched at the top level.

Editing a mesh-only part (no STEP exists): do the boolean in manifold3d, then
the same steps 3 and 4. Prove the edit with a guard region round it: subtract
the guard from the old and new meshes and assert the rest is identical.

## Design discipline

- **Diagnose numerically before redesigning.** When a printed part fails
  (grinds, wobbles, doesn't fit), measure the interference from the CAD and the
  mating hardware first (e.g. screw-head sweep annulus vs boss radius), then
  change only the offending feature.
- **A proven silhouette is not up for redesign.** When iterating on a working
  part, keep everything that works byte-for-byte and vary the one dimension in
  question. Wholesale reimaginings have been rejected before.
- **Printed-hole fit is a print artifact, not a CAD one.** Elephant's foot
  tightens bed-end bores; `xy_hole_compensation` opens them. Model nominal
  dimensions; emit deliberately-undersized variants only as labeled
  compensation experiments (e.g. `_b2.4`), and prefer slicer knobs for tuning.
- **Say which hand** (Script conventions). A bare "left" is a defect.

## Environment facts

- Python: `C:\cadquery-venv\Scripts\python.exe` (cadquery 2.8, trimesh,
  manifold3d, shapely, ezdxf, numpy, scipy, networkx, matplotlib, VTK 9.6,
  Pillow, rtree; pip is available). `cq_helpers.py` is in its site-packages.
  Its versioned copy lives in this skill at `venv-modules/`; the site-packages
  copy is the installed one. Edit the skill copy, copy it over, run
  `scripts/test_cq_helpers.py` (it asserts the two match).
- That `python.exe` is a small uv trampoline; the real interpreter (CPython
  3.14 under `%APPDATA%\uv\python\`) runs as its CHILD. Anything that measures
  or kills a build by PID must cover the whole tree, which is why the runner
  uses a job object (gotchas: "watch the tree").
- Install extra packages with `C:\cadquery-venv\Scripts\python.exe -m pip
  install ...`, never `uv sync` from some other project folder.

## Modeling from a reference image

When the part comes from an image (drawing, render, photo, sketch) instead of
a text description, do NOT start with a script. Follow
`references/reference-image-decomposition.md`: produce a structured feature
decomposition (saved as `decomposition.md`), get the user's confirmation, then
build against the file. Mid-build and before declaring done, run
`h.render_compare(solid, ref_image, out_png)` and actually read the PNG
against the reference. Skip the decomposition only when the user has already
described the part in plain text.

`render_compare` confirms the gross silhouette and feature count only: its
views are orthographic, but its reference panel is shrunk to about 400 px,
so it still cannot check placement. For anything placed off the drawing
(undimensioned hole positions), calibrate px/mm PER VIEW from a callout in that
view (two views of one drawing can differ in scale; one test drawing's
differed by 6.5 percent) and overlay the model's projected edges on the drawing
at that scale.

## Before heavy or unfamiliar ops

Read `references/gotchas.md`: the OCCT/toolchain landmines that have actually
bitten: fuse validity on coplanar/tangent bites, ShapeFix masking, makeCone
equal-radii, non-uniform scale turning faces into B-splines,
Onshape-STEP tessellation cracks, float32 STL collapsing sub-micron edges, the
manifold3d mesh-only path and swept-bevel ridges, chain drift, the
painter-sort renders that faked see-through, edge selection, why the watchdog
must cover the whole process tree, and floating islands that every fit gate
misses.

## Recording

- Ready to print: hand over the STL name, the print orientation the island
  check used, and what it flagged. A print plan (printer, material,
  orientation, supports) belongs in the part folder, tied to that STL.
- Print result back (fits, grinds, wobbles): update the script's `STATUS:`
  line; a fitted part is FROZEN.
- Session end: what changed, what is proven and which file to print go in the
  part's README, not only in chat. A lesson that applies beyond one part goes
  in `references/gotchas.md` with the date and the part it bit.
