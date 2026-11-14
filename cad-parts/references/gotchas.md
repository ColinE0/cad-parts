# OCCT / toolchain gotchas (each one has actually bitten)

## Non-uniform scaling turns every face into a B-spline
`transformGeometry` with a non-uniform scale converts every analytic face
(cylinders, cones, tori) into BSplines. The result stays valid and its volume
exact, but later operations get fragile: an offset (+0.3 mm) that works on the
analytic part fails on the stretched one, and the mesh comes out about twice as
dense. Avoid it: rebuild the part
parametrically from primitives, cut the analytic features off before scaling,
or (for print-bound parts) scale the STL *mesh* instead of the B-rep.

This op was first blamed for the 2026-07-14 crash, when a long-lived CAD server
process ran out of memory and took the whole machine down. A replay on 2026-11-14
(CadQuery 2.8, OCCT 7.9) of the same scale on the same ~98-face imported STEP
finished in 0.24 s at 0.68 GB committed, valid and volume-exact. The crash came
from the long-lived process (imported models accumulating across calls), not
from the scale. That is still why every run is a one-shot subprocess under the
RAM watchdog.

The mesh route, proven in the 2026-10-05 eval (a filleted, holed puck stretched
1.2x in X: 1.38 GB peak, 7.9 s, watertight):

```python
import numpy as np, trimesh
v, f = shape.tessellate(0.05, 0.1)     # mm, rad; lower tol = closer volume
mesh = trimesh.Trimesh(np.array([(p.x, p.y, p.z) for p in v]), np.array(f), process=True)
assert len(mesh.faces) < 60000         # mesh_to_solid takes ~10 s per 36k triangles
mesh.apply_scale(np.array((sx, sy, sz), dtype=float))
solid = h.mesh_to_solid(h.snap_float32(mesh))
h.export_checked(solid, base, step=False, stl_dir="stl")
```

It yields a printable STL and NO useful STEP. When a STEP must come back,
rebuild from primitives at the new size instead.

## Triage a cap kill (exit 137, "hit the 4 GB cap")
1. Cap or timeout? The runner's last line names which. A cap kill seconds into
   a 300 s budget is an allocation problem, not a slow job.
2. Read the committed totals the script printed in `<script>.out.txt`. Linear
   growth with no plateau is a runaway: something is held across iterations
   (models appended to a list, re-imported STEPs) or an op is exploding. A
   climb that levels off just above the cap is a
   genuinely heavy job.
3. Only the second case justifies raising `-MaxRamGB`, and only by a step.
   For the first, fix the geometry or drop the references, then re-run at the
   default cap. The peak can read slightly above the cap because Windows
   counts the refused allocation; the tree never held more.

## The watchdog must watch the tree, not the trampoline
`C:\cadquery-venv\Scripts\python.exe` is a 45 KB uv trampoline that spawns the
real interpreter as a child. The original runner polled the trampoline's own
working set: an 800 MB probe reported "peak RSS 0.01 GB" (2026-09-14), so the
4 GB cap could never fire. Its timeout kill (Stop-Process on the trampoline)
also orphaned anything the script had spawned: a subprocess's trampoline and
interpreter both kept running (2026-09-15). Only the direct interpreter died,
and only because uv's own job object ties it to the trampoline.
Fixed 2026-09-15: `run_watchdogged.ps1` starts the trampoline suspended inside
a job object (job-wide commit limit, kill-on-close) before it can spawn
anything, so the cap, the peak and every kill cover the whole tree, and a dead
runner takes the tree with it. Verified that day: 800 MiB under
`-MaxRamGB 0.5` killed in 1.5 s while the script tried to linger, nothing
surviving; the default cap reports a 0.79 GB peak; a 4 s timeout kills the
interpreter plus a spawned grandchild; hard-killing the runner's pwsh kills
the tree; Windows PowerShell 5.1 runs it too.
Reading the numbers:
- The figure is committed memory (what exhausts the machine), not working
  set. Importing cadquery alone commits about 0.7 GB.
- Windows counts a REFUSED allocation in the peak, so after a cap kill the
  peak can read above the cap; the runner prints a note saying so. The tree
  never actually held more than the cap.
- Never watch or kill a build by the trampoline's PID alone.
In-script caps (a job object a script arms on itself)
still arm fine inside the runner as nested jobs, but the runner now enforces a
cap on its own.

## Fuse validity on coplanar / near-tangent geometry
A boolean whose pieces only kiss (shared face, hairline overlap) can return an
INVALID solid. Observed: a 0.2 mm wall bite left `fuse` invalid; deepening the
bite to 0.6 mm produced a clean valid solid with no repair needed.
- Prefer a real overlap (0.5 mm+) over a tangent or sliver contact.
- To localize a bad fuse in a multi-piece union, bisect: fuse piece by piece
  and check `isValid()` after each.
- `ShapeFix_Shape` can silently mask the problem (returns "valid" geometry that
  meshes with cracks). Treat needing ShapeFix as a design smell; fix the
  geometry instead. A fuzzy fuse (`fuse(x, tol=...)`) did NOT fix validity when
  tried.

## Onshape-exported STEP files mesh with hairline cracks
An untouched Onshape STEP can tessellate to a non-watertight STL (seen: 4 open
edges on `Base Plate (2).step` with no edits at all). `export_checked`
auto-repairs this (gentle `merge_vertices` + `fill_holes`, volume-drift
guarded). If an import-based part fails the gate, suspect the SOURCE file
before your edit: export the unedited import and check it.

## A mesh pinned on your shape never reaches export_checked's STL: use mesh=
Bit 2026-10-12 (mecanum hub cheeks, D3.4 roller sockets). Since 2026-10-11 `export_checked` writes
its STL from `shape.copy()` (so the caller's shape stays unmeshed), and `copy()` drops the
triangulation: the old recipe of pinning the mesh on the part first (`BRepTools.Clean_s` +
`BRepMesh_IncrementalMesh(part.wrapped, 0.05, False, 0.2, False)`, then `export_checked`) silently
lost the pin, and the STL came out at CadQuery's exporter defaults (0.1 relative, 0.1 rad). The
vendor plain cheek's sliver faces leak there: re-imported, it fails the gate at the defaults
(132385 faces, open) and passes pinned (41672). Pin it on the copy instead:
`h.export_checked(part, base, mesh=(0.05, 0.2))` (Clean_s, then BRepMesh_IncrementalMesh at
deflection mm absolute and angular rad, not parallel, and the STL written from that mesh; byte
for byte the hub-cheek scripts' own pinned write, test group 12). `mesh=None` keeps the defaults.
When the shape handed over already carries a mesh, `export_checked` prints an "export_checked
note" line: if that mesh was meant for the STL, pass `mesh=`.

## Float32 STL collapses sub-micron edges
STL stores float32 (about 1e-5 mm resolution at 100-300 mm), so two distinct
double-precision vertices closer than that merge on reload: degenerate faces
and edges shared by 4-6 faces, even though the in-memory mesh was watertight
and the OCCT solid was valid. Bit 2026-09-21 (a box lid with a
logo cut from a DXF): the DXF repeats the first point of 40 loops just before
the closing point, up to 3.5e-4 mm off, and the recess walls carried those
slivers. export_checked caught it, and its merge-and-fill repair could not
fix it. Dedupe consecutive profile points (1e-3 mm) before extruding
(`h.dedupe_points(pts, eps=1e-3)`).
Booleans make their own sub-micron edges too (2026-09-22: a 45 deg bevel
left ~400, 1e-9 to 1e-4 mm, where neighbouring bevel faces meet a wall).
manifold3d's `simplify` and `set_tolerance` did NOT remove them. What works:
snap to float32 and rebuild, `res = m3d.Manifold(res.to_mesh())`; the
constructor collapses the edges the rounding zeroed. Then assert the
vertices are float32-exact, which is the real invariant.
`h.snap_float32(mesh)` does the rebuild and both asserts.

## Mesh-only parts still go through export_checked
When the part only exists as an STL, do the boolean in manifold3d (in the
venv; `Mesh64` keeps doubles, `FillRule.EvenOdd` reads nested DXF loops),
then wrap the result as an OCCT solid: fill a `Poly_Triangulation`, run
`BRepBuilderAPI_MakeShapeOnMesh`. It returns a COMPOUND of faces, and it
silently DROPS zero-area triangles (the float32 snap leaves a few
collinear one-step slivers), so sew the compound
(`BRepBuilderAPI_Sewing(1e-5)`, assert 0 free edges) rather than stacking
faces into a shell, then `MakeSolid` + `BRepLib.OrientClosedSolid_s`. 36k
triangles sew and validate in about 10 s; export with `step=False`.
Ported as `h.mesh_to_solid(mesh)`, so a script no longer needs the OCP
imports.

## Swept bevels: keep the sweep's ridge off the wall
A chamfer on a recess built as the union of per-segment hulls of 45 deg
cones puts each hull's apex ridge exactly on the recess wall. manifold3d
resolves that tangency with coincident-but-distinct vertices (536 of them
along the crease, 2026-09-22), and any merge by position (STL reload,
trimesh) turns them into non-manifold edges. Centre the cones 0.02 mm
inside the recess (radius +0.02) so the bevel crosses the wall cleanly.

## makeCone rejects equal radii
`cq.Solid.makeCone(r, r, h)` raises. Branch: if the radii are (nearly) equal,
make a cylinder instead.

## Edge selection: BoxSelector beats string chains
Chained string selectors like `.edges(">>Z[0] or <Z").edges(RadiusNthSelector(-1))`
are brittle across geometry tweaks. Two robust patterns:
- `part.faces("<Z").edges().chamfer(...)` applied EARLY, while the target face
  is still a clean circle (before cuts complicate it). Order matters: chamfer
  or fillet first, cut second.
- `cq.selectors.BoxSelector((x0,y0,z0), (x1,y1,z1), boundingbox=True)` to grab
  edges by location.

## Renders: matplotlib's painter sort fakes see-through
matplotlib's `Poly3DCollection` has no depth buffer. It sorts whole triangles
by their MEAN depth and paints far to near, so a long triangle that is near the
eye where it covers something, but has its centroid far back, is painted FIRST
and small triangles behind it land on top. Multi-part renders showed parts
through each other that were not touching: bit 2026-10-09 (a racecar
concept), green PCB streaks through the red engine cover and the yellow bed
while `h.interference` measured 0.000 mm3; the IMX462 mount assemblies showed
the deck through the chassis walls. Single parts got it too, as a dark
triangle on a flat face in the 3/4 view that looked like a hole (the
2026-10-05 eval bracket, a clean solid).
Since 2026-10-09 `render6` and `render_compare` draw with VTK offscreen
(z-buffer, parallel projection, normals split at 35 deg) and use matplotlib
only to lay out the panels; test group 11 is a plate-over-sphere case the old
renderer failed. For a multi-colour assembly call `h.render_views(items,
png, views)` (same renderer, one colour per item, titles and legend). A render is still never
an interference check: measure with `h.interference`. A dark patch in a VTK
view is a surface facing away from the camera lights (a down-facing chamfer
seen through a window, 2026-10-09), so ray-cast before calling it a defect.
In any script that still builds its own matplotlib 3D plot:
`Poly3DCollection(..., edgecolors="none", shade=True)` crashes in
`_shade_colors` (pass `facecolors` + `shade=True`, omit `edgecolors`), and call
`matplotlib.use("Agg")` before pyplot.

## Chain drift: a dependent pinned to a parent that moved on
Sled v13 to v15 point `PLATE` at a base-plate STEP that no longer exists in
the plate folder (the chain moved to step 8c, then 10c), so they do not run;
v16 pins step 8c and passed every check while the plate to print was 10c
(folder READMEs, 2026-09-22). A pinned filename fails silently in the worse
direction too: the checks pass against a parent that is not on the robot.
Use `current.json` in the chain folder plus `h.import_current(folder,
pin=...)`: the build fails naming both parts when the chain has moved.

## cq.Solid.makeSphere makes a HEMISPHERE by default
Its defaults are `angleDegrees1=0, angleDegrees2=90`: latitudes 0..90, the upper half only,
whatever its docstring says. `Workplane.sphere()` is full (-90..90). Bit 2026-09-27 (a robot's
rear caster): the ball cavity was cut with a default makeSphere, so the retaining lip and the
opening were never cut and the cup came out closed, and the fit gate PASSED because the test ball
was built the same way. Pass `-90, 90, 360` explicitly, assert a sphere's bbox height equals its
diameter, and gate a cavity with a probe that does not reuse the primitive under suspicion.

## PCB clearance: filter parts by where they END, never where they start
Through-hole parts in a board STEP start BELOW the board top: their pins run through it. A
"top-side parts" filter written as `bbox.zmin >= board_top` silently drops them. Bit 2026-09-26
(a camera mount): it dropped a 1x10 female header standing 8.5 mm tall, the height map
called that area bare board, and the over-body camera mount was designed onto it; only the
build's own interference gate caught it. Count every solid with `bbox.zmax > board_top`, and
still run the true `h.interference` against the real board solids before trusting a map.

## Fit gates are not print gates: floating islands
Bit 2026-10-09 (a robot's long-tail shell, three colours, a 22 h print). The sled tunnel cut away
the foot of the pillar between the wheel wells, so, printed upright, the pillar started 5.65 above
the bed on tree supports and stood 36.8 tall, 6.52 thin front to back, before the arch crowns tied
it in at z 49.98. It snapped off partway through. Every gate in the build log had passed (0 overlap
with 347 chassis solids, wheels clear, lifts straight off): they all asked "does it fit", none
asked "can it be built bottom-up". The print plan even listed "the sled tunnels' tops" as expected
support without asking what stood on them. Any cut that opens the underside of something (a
tunnel, a notch, a well cut "straight down") can leave the material above it hanging.
`h.islands(part, up=...)` finds these in seconds. Run it in the PRINT orientation, not the
modelled one, and treat a HIGH island as a design change (ground it to the bed, tie it in low,
or re-orient), never as a support setting.

## Engraved text: gate the narrowest feature, not the cap height
Bit 2026-10-11 (a robot base plate, "START" / "RESET" 0.6 deep in the bed face). Impact at a
4.9 mm cap passed every check (inside its window, recess volume equal to ink area x depth, reads the
right way from below) and the slicer still mangled the S's, START's second T and the top of the A.
The failures were the PLASTIC between strokes (the S's slits, the A's apex, an R almost touching
the next T), not the strokes: a condensed display face packs both under two extrusion lines. Gate
both in 2D with shapely: the engraved region and the plastic around it (a round-cornered frame,
so its own corners never read thin), each opened by MIN_FEAT / 2 (0.45 for a 0.4 nozzle) after
dropping corner fringes under 0.2 wide; fail on anything left. What passed: Segoe UI Bold, letters
placed one by one 1.0 apart ink to ink (not kerned), then the outline cleaned to the nozzle (strokes
under 0.9 trimmed, plastic under 0.9 merged into the engraving). That rounds every corner to 0.45 and
shortens the A's counter a little. Of nine Windows fonts tested at 5 to 6 mm caps, Impact, Tahoma Bold and Arial Black
failed on plastic, and Arial Bold, Segoe UI Semibold and Bahnschrift on strokes.

## A HIGH island that is only a mesh crack (and the mesh call that dirties the solid)
Bit 2026-10-11 (a robot's long-nose shell). `h.islands(shape)` reported a 16.8 tall HIGH island
over the grille. The exact OCCT section was ~1306 mm2 at every layer there, but the raw
tessellation had 10 open edges along a face seam, so some mesh slices dropped to ~505 mm2 (the
open loop never closed into a polygon) and the material above looked unsupported.
**`islands()` now handles both of this entry's mesh problems itself (fixed 2026-10-11):** it
tessellates a `copy()` of a shape, so the caller's solid is never meshed, and an open mesh (from
a shape, a trimesh or an STL) gets `export_checked`'s own gentle merge before slicing (shared
helper `_close_cracks`: merge_vertices 5 then 4, fill_holes, kept only if watertight and the
volume moved under 0.5 %), so a seam crack no longer reads as an island and a real one is still
found (test group 10: a cracked column reads clean, a cracked pendant still reads HIGH; the
long-tail shell still reads its 36.8 tall wheel-gap pillars HIGH). If it prints "open mesh a
gentle vertex merge did not close", the crack is too wide for that merge and an island there may
still be false: before redesigning for it, compare the exact section area
(`shape.intersect(thin z slab)`) against the mesh slices. A real island survives the merge, a crack
does not. Two causes found in the same build:
- **Near-coplanar faces from rounded profile points.** One profile's point on a shared plane was
  written `round(face_y(36), 4)`; the other profile's face lay on the exact line. The 4e-6 mismatch
  left a seam that `clean()` would not merge: the mesh cracks, and the faces it crossed. Put shared
  points on the same expression, unrounded.
- **Tessellating a shape can make it read invalid afterwards.** `shape.tessellate(...)` meshes the
  CALLER'S shape in place; when `islands()` still did that, it loosened this shell's tolerances so
  `isValid()` turned False and `export_checked` refused it, though it was valid when built.
  Every cq_helpers function that meshes now meshes a `copy()` and leaves the caller's shape
  unmeshed: `islands()`, the render helpers (`render6`, `render_compare`, `render_views` on a
  shape; a multi-object Workplane's compound is copied too, since it shares its members' faces),
  `interference(clearance=True)` and `export_checked`'s STL write (CadQuery's `exportStl` meshes
  the shape it writes, so it is handed a copy; the STEP export does not mesh; a mesh pinned on
  your shape is dropped with it, so pin the STL's with `mesh=`, see "A mesh pinned on your
  shape never reaches export_checked's STL") (all 2026-10-11;
  test groups 1, 3, 10 and 11 assert it). The copy is cheap: about 13 ms and 1 MB on the 700-face
  long-nose shell, next to about 500 ms for the mesh itself, and the shell's STL came out
  byte-identical (19274 triangles) once `export_checked` wrote it from a copy. Calling
  `tessellate()` or `cq.exporters.export(..., ".stl")` yourself still meshes your shape in place:
  in your own scripts hand them a `shape.copy()`, and assert validity again just before export.
  Separately, a boolean colour split on the long in-memory solid came out invalid while the same
  cut on the re-imported STEP was clean: for multi-colour splits, export the one-body STEP first and
  split the re-import (the colour bodies then come from exactly the file written).
More from the same build's rear, all coincidences of exact numbers:
- **An edge exactly on a slice plane.** `islands()` slices at bed + layer * (k + 0.5). A diffuser
  ramp whose top edge sat exactly at one of those heights (z 19.20 = bed 7.5 + 11.7) made that
  slice degenerate, and the end fence standing on the ramp read as a 2.4 tall HIGH island "to
  never", though it was a solid fin from the bed (the exact section showed it continuous). Nudging
  the slope 0.68 to 0.67 cleared it. If an island starts right where an edge's z is a multiple of the
  layer plus half, suspect this before redesigning.
- **A colour region's corner landing exactly on a solid face.** A black colour split whose mitred
  corner touched the side face of the block it was cut into left the GREY body with two edges
  shared by four faces: the grey STL failed `export_checked` as not watertight, with zero open
  edges (count edge use: `Counter(map(tuple, mesh.edges_sorted))`; a 4 is a knife-edge contact).
  Move the face or round the region's corner so they do not meet along a line.
- **Profiles eroded with their bottoms dropped straight down.** The shell's hollow is each 2D
  profile offset inward with its first and last points dropped below the floor. When one profile's
  rear (the cabin's, y 71) stood behind another's lower face (the body's, y 66), the dropped cabin
  hollow cut away the body's whole lower rear wall, silently: the next cut "removed nothing". Every
  profile that meets a face must reach the floor through the same points.

## Print-vs-CAD boundary
A vertical bore that measures tight at one end and loose at the other on the
printed part is NOT modeled asymmetry: elephant's foot squeezes the bed-end
first layers while `xy_hole_compensation` opens the bore generally. Check the
model is uniform, then fix in the slicer (or emit labeled undersized variants
like `_b2.4` as a compensation experiment).

## Venv trap
`uv sync` run from some other project folder (or with `UV_PROJECT_ENVIRONMENT`
pointing at this venv) can prune or reinstall the wrong environment. Install
packages with `C:\cadquery-venv\Scripts\python.exe -m pip install ...` only.
