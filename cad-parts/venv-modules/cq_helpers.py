# Copyright 2026 Colin Ezra Wilder. SPDX-License-Identifier: Apache-2.0
"""Shared export/QA helpers for the cad-parts CadQuery subprocess scripts.

Lives in the cadquery-venv site-packages so any one-shot script can just
`import cq_helpers`. Jobs:

  export_checked(shape, basepath)  -> STEP + STL export with a trimesh
      watertight gate on the STL (catches slicer 'non-manifold' errors at
      build time; BRep isValid() alone does not guarantee a clean mesh).
      mesh=(deflection, angular) pins the STL's tessellation.
  render6(shape, png_path)         -> 6 canonical shaded views to one PNG
      (VTK offscreen with a depth buffer since 2026-10-09).
  render_compare(shape, ref, png)  -> reference image beside 3 shaded views,
      the before-done gate for any part modeled from a reference image.
  render_views(items, png, views)  -> the same renderer for assemblies: each
      (shape, colour) in its own colour, any views, titles and a legend.
  describe(shape)                  -> geometry truth block (counts, volume,
      area, bbox, center of mass); diff(before, after) -> per-op delta;
      is_noop(delta) -> catches OCCT silently returning input unchanged.
  interference(a, b)               -> boolean-common overlap volume/bbox
      between two solids, optional approximate clearance when disjoint.
  hints_for_error(msg)             -> actionable fixes for cryptic OCCT
      errors; installed as an excepthook on import, so an uncaught crash
      in a one-shot script prints HINT lines after the traceback.
  set_current(folder, step) / import_current(folder, pin=None)
                                   -> chain pointer for parts edited on an
      imported STEP: current.json names the live parent and its
      fingerprint; a pinned dependent fails loudly when the chain moves.
  dedupe_points / snap_float32 / mesh_to_solid
                                   -> the mesh-path recipes from the
      2026-09-21/22 float32 and manifold3d gotchas, as functions.
  glyph / fit_text_size            -> engraved letters sized to a window
      (pocket labels, L/R marks).
  islands(part, up="+z")           -> floating islands in the print
      orientation: material that starts above the bed and only joins the
      grounded part layers later (a robot shell's pillar, 2026-10-09).

describe/diff/is_noop/hints are ported from jarvis-cadquery-mcp's truth.py
(the MCP server is retired; this is the surviving useful core).
"""
import sys

import cadquery as cq

_LEN = 4   # rounding digits for mm values
_VOL = 3   # rounding digits for mm^2 / mm^3 values


def _val(shape):
    """Normalize Workplane -> Shape; pass Shapes through."""
    return shape.val() if hasattr(shape, "val") else shape


def _close_cracks(m):
    """Hairline tessellation cracks (seen with Onshape-exported STEPs, and on
    face seams of CadQuery's own meshes) usually close with a gentle vertex
    merge. Returns (closed copy, digits) when merging at 5, then 4 digits and
    filling holes makes m watertight without moving its volume 0.5 %, else
    None. m itself is left as it was."""
    import trimesh
    vol0 = m.volume
    for digits in (5, 4):
        mm = m.copy()
        mm.merge_vertices(digits_vertex=digits)
        mm.update_faces(mm.nondegenerate_faces())
        trimesh.repair.fill_holes(mm)
        trimesh.repair.fix_normals(mm)
        if mm.is_watertight and abs(mm.volume - vol0) < 0.005 * abs(vol0):
            return mm, digits
    return None


def _has_mesh(shape):
    """True if any face of shape already carries a triangulation."""
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    return any(BRep_Tool.Triangulation_s(f.wrapped, TopLoc_Location()) is not None
               for f in shape.Faces())


def export_checked(shape, basepath, stl=True, step=True, stl_dir=None, mesh=None):
    """Export shape to basepath('.step'/'.stl'). Asserts BRep validity and,
    for STL, mesh watertightness via trimesh. Returns the trimesh mesh (or
    None if stl=False). stl_dir (e.g. "stl", the house rule since 2026-09-29)
    writes the STL into that subfolder beside basepath instead of next to
    the STEP, creating it if missing. The STL auto-repair closes hairline
    tessellation cracks on a valid B-rep only: it will not close a missing
    face (its volume guard compares against the still-open mesh), so a broken
    mesh someone hands over goes through mesh_to_solid first. The STL is
    written from a copy, so shape itself is left unmeshed, and the copy is
    meshed fresh: a mesh the caller pinned on shape beforehand does NOT reach
    the STL. mesh=(deflection, angular) pins it on the copy instead
    (Clean_s, then BRepMesh_IncrementalMesh at deflection mm absolute and
    angular rad, not parallel) and writes the STL from that triangulation;
    None keeps CadQuery's exporter defaults (0.1 relative, 0.1 rad). The
    mecanum hub cheeks need mesh=(0.05, 0.2): their vendor sliver faces leak
    at other settings (2026-10-12)."""
    if hasattr(shape, "val"):          # accept Workplane or Shape
        shape = shape.val()
    if mesh is not None:
        dfl, ang = mesh
        assert dfl > 0 and ang > 0, f"mesh=(deflection, angular) must both be > 0, got {mesh}"
    assert shape.isValid(), f"{basepath}: BRep solid is not valid; refusing to export"
    wp = cq.Workplane(obj=shape)
    step_path = basepath + ".step"
    if step:
        cq.exporters.export(wp, step_path)
    m = None
    if stl:
        if stl_dir:
            import os
            d = os.path.join(os.path.dirname(basepath), stl_dir)
            os.makedirs(d, exist_ok=True)
            basepath = os.path.join(d, os.path.basename(basepath))
        # exportStl meshes the shape it writes in place: hand it a copy, so the
        # caller's shape stays unmeshed (see islands()); STEP does not mesh.
        # copy() drops the triangulation, so a mesh pinned on shape is lost
        # unless it is pinned on the copy through mesh=
        c = shape.copy()
        if mesh is None:
            if _has_mesh(shape):
                print("export_checked note: shape already carries a mesh, which the STL does not "
                      "use (it is written from a fresh copy at the exporter's defaults); if that "
                      "mesh was pinned for the STL, pass mesh=(deflection, angular)", flush=True)
            cq.exporters.export(cq.Workplane(obj=c), basepath + ".stl")
        else:
            from OCP.BRepMesh import BRepMesh_IncrementalMesh
            from OCP.BRepTools import BRepTools
            BRepTools.Clean_s(c.wrapped)
            BRepMesh_IncrementalMesh(c.wrapped, dfl, False, ang, False)
            c.exportStl(basepath + ".stl", tolerance=dfl, angularTolerance=ang,
                        relative=False, parallel=False)
        import trimesh
        m = trimesh.load(basepath + ".stl")
        if not m.is_watertight:
            # hairline tessellation cracks: try a gentle vertex merge before failing
            fixed = _close_cracks(m)
            if fixed:
                m, digits = fixed
                m.export(basepath + ".stl")
                print(f"stl auto-repaired (merge digits={digits})", flush=True)
        assert m.is_watertight, (
            f"{basepath}.stl is NOT watertight ({len(m.faces)} faces) - "
            "slicer will flag non-manifold; do not print")
        assert m.is_winding_consistent, f"{basepath}.stl has inconsistent winding"
        pinned = "" if mesh is None else f" (mesh {dfl} / {ang})"
        print(f"export ok: {basepath}.stl watertight, {len(m.faces)} faces, "
              f"vol={m.volume:.0f}{pinned}", flush=True)
    if step:
        print(f"export ok: {step_path}", flush=True)
    return m


# ── Renders (VTK offscreen, depth-buffered) ──────────────────────────────
# matplotlib's Poly3DCollection has no depth buffer: it paints whole
# triangles ordered by mean depth, so small far triangles land on top of long
# near ones and assemblies showed parts through each other that did not touch
# (a racecar concept, 2026-10-09). VTK draws with a z-buffer; matplotlib
# only lays the finished panels out with their titles.

_RENDER_BG = (0.957, 0.961, 0.969)


def _shape_tris(shape, tol):
    """Workplane (every Shape on its stack) or Shape -> (N, 3, 3) triangles.
    tol is tessellate()'s linear deflection in mm, as it always was. Meshes a
    copy, so the caller's shape stays unmeshed (see islands())."""
    import numpy as np
    if isinstance(shape, cq.Workplane):
        objs = [o for o in shape.vals() if isinstance(o, cq.Shape)]
        shape = objs[0] if len(objs) == 1 else cq.Compound.makeCompound(objs)
    # copy after compounding: the compound shares its children's faces, so
    # meshing it would mesh every shape on the caller's stack
    verts, tris = shape.copy().tessellate(tol)
    if not tris:
        raise ValueError("render: the shape tessellated to no triangles (empty, or not a solid)")
    pts = np.array([(v.x, v.y, v.z) for v in verts], dtype=np.float64)
    return pts[np.array(tris)]


def _polydata(T):
    """(N, 3, 3) triangles -> vtkPolyData with normals split at 35 deg, so
    curved faces shade smooth and box edges stay crisp."""
    import numpy as np
    from vtkmodules.util import numpy_support as ns
    from vtkmodules.vtkCommonCore import vtkPoints
    from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
    from vtkmodules.vtkFiltersCore import vtkCleanPolyData, vtkPolyDataNormals

    pts = vtkPoints()
    pts.SetData(ns.numpy_to_vtk(np.ascontiguousarray(T.reshape(-1, 3), dtype=np.float64), deep=True))
    n = len(T)
    cells = vtkCellArray()
    cells.SetData(ns.numpy_to_vtkIdTypeArray(np.arange(0, 3 * n + 1, 3, dtype=ns.ID_TYPE_CODE), deep=True),
                  ns.numpy_to_vtkIdTypeArray(np.arange(3 * n, dtype=ns.ID_TYPE_CODE), deep=True))
    pd = vtkPolyData()
    pd.SetPoints(pts)
    pd.SetPolys(cells)
    clean = vtkCleanPolyData()
    clean.SetInputData(pd)
    nrm = vtkPolyDataNormals()
    nrm.SetInputConnection(clean.GetOutputPort())
    nrm.SetFeatureAngle(35.0)
    nrm.SplittingOn()
    nrm.ConsistencyOn()
    nrm.Update()
    return nrm.GetOutput()


def _render_views(items, views, size, bg=_RENDER_BG, frame=None):
    """Draw items [(triangles (N, 3, 3), rgb), ...] once per (elev, azim) in
    views and return one (h, w, 3) uint8 array per view. Angles follow
    matplotlib's view_init: the eye sits along (cos e cos a, cos e sin a,
    sin e) from the part, screen-up is +z tilted back toward the eye's
    azimuth (so elev 90 at azim -90 keeps +y up, as matplotlib did).
    Parallel projection, each view framed on the triangles' own extent, or
    on the box frame = (xmin, xmax, ymin, ymax, zmin, zmax) when given."""
    import math
    import numpy as np
    import vtkmodules.vtkRenderingOpenGL2  # noqa: F401  (registers the OpenGL backend)
    from vtkmodules.util import numpy_support as ns
    from vtkmodules.vtkRenderingCore import (vtkActor, vtkLightKit, vtkPolyDataMapper,
                                             vtkRenderer, vtkRenderWindow,
                                             vtkWindowToImageFilter)

    pts = np.concatenate([T.reshape(-1, 3) for T, _ in items])
    if frame is not None:
        x0, x1, y0, y1, z0, z1 = frame
        box = np.array([(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], dtype=np.float64)
        # the eye backs off past everything drawn, not just the framed box
        span = np.concatenate([pts, box])
        diag = float(np.linalg.norm(span.max(0) - span.min(0))) or 1.0
        pts = box
    lo, hi = pts.min(0), pts.max(0)
    mid = (lo + hi) / 2.0
    rel = pts - mid
    if frame is None:
        diag = float(np.linalg.norm(hi - lo)) or 1.0
    ren = vtkRenderer()
    ren.SetBackground(*bg)
    ren.TwoSidedLightingOn()
    for T, rgb in items:
        mapper = vtkPolyDataMapper()
        mapper.SetInputData(_polydata(T))
        actor = vtkActor()
        actor.SetMapper(mapper)
        pr = actor.GetProperty()
        pr.SetColor(*rgb)
        pr.SetAmbient(0.22)
        pr.SetDiffuse(0.78)
        pr.SetSpecular(0.12)
        pr.SetSpecularPower(25.0)
        ren.AddActor(actor)
    vtkLightKit().AddLightsToRenderer(ren)    # camera lights: they follow every view
    ren.UseFXAAOn()
    rw = vtkRenderWindow()
    rw.SetOffScreenRendering(1)
    rw.AddRenderer(ren)
    rw.SetSize(*size)
    w2i = vtkWindowToImageFilter()
    w2i.SetInput(rw)
    w2i.ReadFrontBufferOff()
    cam = ren.GetActiveCamera()
    cam.ParallelProjectionOn()
    aspect = size[0] / size[1]
    out = []
    try:
        for elev, azim in views:
            e, a = math.radians(elev), math.radians(azim)
            eye = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
            up = np.array([-math.sin(e) * math.cos(a), -math.sin(e) * math.sin(a), math.cos(e)])
            right = np.cross(-eye, up)
            r, u = rel @ right, rel @ up
            focal = mid + right * (r.min() + r.max()) / 2.0 + up * (u.min() + u.max()) / 2.0
            half_w, half_h = (r.max() - r.min()) / 2.0, (u.max() - u.min()) / 2.0
            cam.SetFocalPoint(*focal)
            cam.SetPosition(*(focal + 2.0 * diag * eye))
            cam.SetViewUp(*up)
            cam.SetParallelScale(1.08 * max(half_h, half_w / aspect) or 1.0)
            ren.ResetCameraClippingRange()
            rw.Render()
            w2i.Modified()
            w2i.Update()
            img = w2i.GetOutput()
            nx, ny, _ = img.GetDimensions()
            arr = ns.vtk_to_numpy(img.GetPointData().GetScalars()).reshape(ny, nx, -1)
            out.append(arr[::-1, :, :3].copy())
    finally:
        rw.Finalize()
    return out


def render6(shape, png_path, color="#b25563", tol=0.3):
    """Render 6 canonical views (front/back/left/right/top/front-3/4) of a
    cadquery Shape or Workplane (every Shape on its stack) to a single PNG.
    Depth-buffered VTK, parallel projection; tol is the tessellation's
    linear deflection in mm."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_rgb

    views = [(0, -90, "front"), (0, 90, "back"), (0, 180, "left"),
             (0, 0, "right"), (90, -90, "top"), (20, -120, "front 3/4")]
    imgs = _render_views([(_shape_tris(shape, tol), to_rgb(color))],
                         [(e, a) for e, a, _ in views], (600, 470))
    fig = plt.figure(figsize=(18, 10.4), dpi=100)
    fig.patch.set_facecolor(_RENDER_BG)
    for i, ((_, _, title), img) in enumerate(zip(views, imgs), 1):
        ax = fig.add_subplot(2, 3, i)
        ax.imshow(img)
        ax.set_axis_off()
        ax.set_title(title, fontsize=11)
    plt.subplots_adjust(left=0, right=1, bottom=0, top=0.96, wspace=0, hspace=0.1)
    plt.savefig(png_path, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"render6 -> {png_path}", flush=True)


def render_compare(shape, ref_image_path, png_path, color="#b25563", tol=0.3):
    """Reference image side by side with 3 shaded views (front / top /
    front-3/4) in one PNG. Look at this mid-build and before declaring a
    reference-derived part done: check feature count, placement, and
    proportion against the reference, not against memory. Same renderer
    as render6."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_rgb

    views = [(0, -90, "front"), (90, -90, "top"), (20, -120, "front 3/4")]
    imgs = _render_views([(_shape_tris(shape, tol), to_rgb(color))],
                         [(e, a) for e, a, _ in views], (400, 455))
    fig = plt.figure(figsize=(16, 5), dpi=100)
    fig.patch.set_facecolor(_RENDER_BG)
    ax = fig.add_subplot(1, 4, 1)
    ax.imshow(plt.imread(ref_image_path))
    ax.set_axis_off()
    ax.set_title("reference", fontsize=10)
    for i, ((_, _, title), img) in enumerate(zip(views, imgs), 2):
        ax = fig.add_subplot(1, 4, i)
        ax.imshow(img)
        ax.set_axis_off()
        ax.set_title(title, fontsize=10)
    plt.subplots_adjust(left=0, right=1, bottom=0, top=0.92, wspace=0)
    plt.savefig(png_path, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"render_compare -> {png_path}", flush=True)


def render_views(items, png_path, views, title=None, size=(800, 640), cols=None,
                 legend=None, tol=0.3, frame=None, bg="white"):
    """Multi-colour assembly render, same depth-buffered VTK renderer as
    render6: every item in its own colour, drawn once per view, the views
    laid out in a grid in one PNG.

    items   [(shape, colour), ...] or (shape, colour, tol) to override tol for
            one item. shape is a Shape, a Workplane (every Shape on its stack)
            or an already tessellated (N, 3, 3) numpy triangle array (a script
            that draws one part in many renders tessellates it once); colour is
            anything matplotlib reads ("#b25563", (0.7, 0.3, 0.4), "white").
    views   [(label, elev, azim), ...] in matplotlib's view_init angles: azim
            is the eye's bearing from +x, so the -y front is azim -90. An
            empty label draws no caption.
    size    (w, h) pixels of each view. One view with no label, title or
            legend writes exactly that image.
    cols    views per row; default all of them up to 3, else ceil(sqrt(n)).
    legend  [(colour, label), ...] as swatches along the bottom.
    frame   (xmin, xmax, ymin, ymax, zmin, zmax): frame every view on this box
            instead of the items' own extent (a close-up of a clipped region).
    tol     tessellation linear deflection in mm, as in render6."""
    import math
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_rgb
    from matplotlib.patches import Patch

    tris = []
    for it in items:
        shape, colour = it[0], it[1]
        if isinstance(shape, np.ndarray):
            T = np.asarray(shape, dtype=np.float64)
            assert T.ndim == 3 and T.shape[1:] == (3, 3), f"render_views: triangles must be (N, 3, 3), not {T.shape}"
        else:
            T = _shape_tris(shape, it[2] if len(it) > 2 else tol)
        if len(T):
            tris.append((T, to_rgb(colour)))
    assert tris, "render_views: no item has any triangles"
    imgs = _render_views(tris, [(e, a) for _, e, a in views], size, bg=to_rgb(bg), frame=frame)

    n = len(views)
    cols = cols or (n if n <= 3 else math.ceil(math.sqrt(n)))
    rows = math.ceil(n / cols)
    w, hv = size
    lab = 34 if any(v[0] for v in views) else 0
    top = 50 if title else 0
    bot = 44 if legend else 0
    W, H = cols * w, top + rows * (lab + hv) + bot
    # the half pixel: Agg truncates the canvas size, and 1258 / 100 * 100 is 1257.99...
    fig = plt.figure(figsize=((W + 0.5) / 100, (H + 0.5) / 100), dpi=100)
    fig.patch.set_facecolor(bg)
    for i, ((label, _, _), img) in enumerate(zip(views, imgs)):
        r, c = divmod(i, cols)
        y0 = H - top - (r + 1) * (lab + hv)          # the view's bottom edge, px up from the figure's
        fig.figimage(img, xo=c * w, yo=y0, origin="upper")    # pixel for pixel, no resampling
        if label:
            fig.text((c + 0.5) * w / W, (y0 + hv + lab / 2) / H, label, ha="center", va="center", fontsize=12)
    if title:
        fig.text(0.5, 1 - top / 2 / H, title, ha="center", va="center", fontsize=15)
    if legend:
        fig.legend(handles=[Patch(color=to_rgb(c), label=t) for c, t in legend], loc="lower center",
                   ncol=len(legend), fontsize=11, frameon=False)
    fig.savefig(png_path, dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"render_views -> {png_path}", flush=True)


# ── Geometry truth (ported from jarvis-cadquery-mcp truth.py) ────────────

def describe(shape):
    """Geometry summary of a Workplane/Shape: topology counts, exact volume,
    surface area, bbox size/min/max, center of mass. All values mm/mm^2/mm^3.
    Returns an empty-but-valid block for None/empty input."""
    empty = {
        "solids": 0, "faces": 0, "edges": 0, "vertices": 0,
        "volume_mm3": 0.0, "area_mm2": 0.0,
        "bbox_mm": [0.0, 0.0, 0.0],
        "bbox_min": [0.0, 0.0, 0.0], "bbox_max": [0.0, 0.0, 0.0],
        "center_mass": [0.0, 0.0, 0.0],
    }
    if shape is None:
        return empty
    solid = _val(shape)
    try:
        faces = solid.Faces()
        edges = solid.Edges()
        verts = solid.Vertices()
    except Exception:
        return empty
    if not faces:
        return empty

    bb = solid.BoundingBox()
    try:
        volume = solid.Volume()
    except Exception:
        volume = 0.0
    try:
        area = sum(f.Area() for f in faces)
    except Exception:
        area = 0.0
    try:
        com = solid.Center()
        center = [round(com.x, _LEN), round(com.y, _LEN), round(com.z, _LEN)]
    except Exception:
        center = [0.0, 0.0, 0.0]
    try:
        n_solids = len(solid.Solids())
    except Exception:
        n_solids = 1

    return {
        "solids": n_solids,
        "faces": len(faces),
        "edges": len(edges),
        "vertices": len(verts),
        "volume_mm3": round(volume, _VOL),
        "area_mm2": round(area, _VOL),
        "bbox_mm": [round(bb.xlen, _LEN), round(bb.ylen, _LEN), round(bb.zlen, _LEN)],
        "bbox_min": [round(bb.xmin, _LEN), round(bb.ymin, _LEN), round(bb.zmin, _LEN)],
        "bbox_max": [round(bb.xmax, _LEN), round(bb.ymax, _LEN), round(bb.zmax, _LEN)],
        "center_mass": center,
    }


def diff(before, after):
    """Delta between two describe() blocks: did the cut remove volume, did
    the fillet drop edges, did the translate actually move the body."""
    def d(key, n):
        return round(after.get(key, 0) - before.get(key, 0), n)

    bbox_delta = [round(a - b, _LEN) for a, b in
                  zip(after.get("bbox_mm", [0, 0, 0]), before.get("bbox_mm", [0, 0, 0]))]
    # bbox sizes are blind to rigid moves; center-of-mass delta is the
    # position signal that keeps a translate from looking like a no-op.
    center_delta = [round(a - b, _LEN) for a, b in
                    zip(after.get("center_mass", [0, 0, 0]), before.get("center_mass", [0, 0, 0]))]
    return {
        "volume_delta_mm3": d("volume_mm3", _VOL),
        "area_delta_mm2": d("area_mm2", _VOL),
        "bbox_delta_mm": bbox_delta,
        "center_delta_mm": center_delta,
        "solids_delta": int(after.get("solids", 0) - before.get("solids", 0)),
        "faces_delta": int(after.get("faces", 0) - before.get("faces", 0)),
        "edges_delta": int(after.get("edges", 0) - before.get("edges", 0)),
    }


def is_noop(changes):
    """True if a diff() shows no geometric change at all. OCCT sometimes
    returns the input unchanged instead of raising (e.g. a shell it cannot
    offset); assert not is_noop(...) after an op that must change geometry."""
    if not changes:
        return False
    scalars = ["volume_delta_mm3", "area_delta_mm2", "solids_delta",
               "faces_delta", "edges_delta"]
    if any(changes.get(k, 0) for k in scalars):
        return False
    return (not any(changes.get("bbox_delta_mm", []))
            and not any(changes.get("center_delta_mm", [])))


# ── Interference / clearance ─────────────────────────────────────────────

def _min_surface_distance(target_mesh, points, best=float("inf")):
    """Minimum distance from any of `points` to the surface of `target_mesh`,
    exact for those points and memory-bounded.

    Points are visited in order of their distance to the target's bounding box
    (a lower bound on the true distance) and the loop stops as soon as that
    bound reaches the best distance found. Each point queries the target's
    triangle r-tree with a box of half-size `best`, so only triangles that
    could improve the answer are ever loaded; trimesh's own closest_point
    sizes that box by the nearest VERTEX distance instead, which on a dense
    plate mesh meant thousands of candidate triangles per point and a
    (12 M x 3) array that hit the 4 GB cap (step 10c plate vs sled,
    2026-09-26). `best` may be seeded with the other direction's result so
    the second direction prunes from the start."""
    import numpy as np
    from trimesh import triangles as _tri
    pts = np.unique(np.asarray(points, dtype=float), axis=0)
    if len(pts) == 0:
        return float(best)
    lo, hi = target_mesh.bounds
    d_box = np.linalg.norm(np.maximum(0.0, np.maximum(lo - pts, pts - hi)), axis=1)
    order = np.argsort(d_box, kind="stable")
    tree = target_mesh.triangles_tree
    kd = target_mesh.kdtree
    tris = target_mesh.triangles
    best = float(best)
    for i in order:
        if d_box[i] >= best:
            break
        p = pts[i]
        r = best if np.isfinite(best) else float(kd.query(p)[0])
        r += 1e-6
        cand = list(tree.intersection((p[0] - r, p[1] - r, p[2] - r, p[0] + r, p[1] + r, p[2] + r)))
        if not cand:
            continue
        q = np.tile(p, (len(cand), 1))
        close = _tri.closest_point(tris[cand], q)
        d = float(np.linalg.norm(close - q, axis=1).min())
        if d < best:
            best = d
    return best


def interference(a, b, clearance=False, tol=0.3):
    """Overlap between two Workplanes/Shapes via OCCT boolean common.

    Returns a dict:
      intersects      bool
      volume_mm3      overlap volume (0.0 when disjoint)
      bbox_mm/min/max overlap region extents (zeros when disjoint)
      clearance_mm    only when clearance=True and disjoint: APPROXIMATE
                      minimum separation (vertex-sampled on tessellated
                      meshes; treat as an estimate, not a gauge reading).
                      Memory-bounded since 2026-09-26: per-point r-tree
                      queries sized by the best distance so far, visited in
                      bbox-distance order with early exit, so a dense plate
                      against a small part no longer blows the RAM cap.

    Use to measure the actual interference numerically (screw-head sweep
    vs boss, wheel swing vs wall) before redesigning anything.
    """
    sa, sb = _val(a), _val(b)
    common = None
    try:
        common = sa.intersect(sb)
    except Exception:
        common = None  # OCCT boolean failure on disjoint/tangent inputs
    vol = 0.0
    if common is not None:
        try:
            vol = common.Volume()
        except Exception:
            vol = 0.0
    out = {
        "intersects": vol > 1e-9,
        "volume_mm3": round(vol, _VOL),
        "bbox_mm": [0.0, 0.0, 0.0],
        "bbox_min": [0.0, 0.0, 0.0],
        "bbox_max": [0.0, 0.0, 0.0],
    }
    if out["intersects"]:
        bb = common.BoundingBox()
        out["bbox_mm"] = [round(bb.xlen, _LEN), round(bb.ylen, _LEN), round(bb.zlen, _LEN)]
        out["bbox_min"] = [round(bb.xmin, _LEN), round(bb.ymin, _LEN), round(bb.zmin, _LEN)]
        out["bbox_max"] = [round(bb.xmax, _LEN), round(bb.ymax, _LEN), round(bb.zmax, _LEN)]
    elif clearance:
        import numpy as np
        import trimesh
        meshes = []
        for s in (sa, sb):
            # mesh a copy so the caller's shapes stay unmeshed (see islands())
            verts, tris = s.copy().tessellate(tol)
            meshes.append(trimesh.Trimesh(
                vertices=np.array([(v.x, v.y, v.z) for v in verts]),
                faces=np.array(tris), process=False))
        d_ab = _min_surface_distance(meshes[1], meshes[0].vertices)
        d_ba = _min_surface_distance(meshes[0], meshes[1].vertices, best=d_ab)
        out["clearance_mm"] = round(min(d_ab, d_ba), _LEN)
    return out


# ── OCCT error hints (ported from truth.py; script-context wording) ──────

_HINT_TABLE = [
    ("no such file", "The referenced file does not exist. Check the path."),
    ("brep_api: command not done",
     "OCCT rejected the operation, usually a fillet/chamfer radius too large "
     "for the edge, or a shell thickness thicker than the wall. Try a smaller value."),
    ("standard_constructionerror",
     "A dimension is zero or negative where it must be positive (radius, depth, thickness)."),
    ("empty",
     "A selector matched no geometry. Print the model's faces/edges "
     "(e.g. solid.faces('>Z').size()) to see what the selector actually picks."),
    ("selector",
     "A selector matched no geometry. Print the model's faces/edges "
     "(e.g. solid.faces('>Z').size()) to see what the selector actually picks."),
    ("fillet",
     "Fillet failed, radius likely exceeds the adjacent face size. "
     "Reduce the radius or select fewer edges."),
    ("chamfer",
     "Chamfer failed, distance likely exceeds the adjacent face size. Reduce it."),
    ("shell",
     "Shell failed, thickness likely exceeds the thinnest wall, or the removed "
     "face set is invalid. Reduce thickness."),
    ("boolean",
     "Boolean failed, the two solids may not intersect (subtract/intersect) "
     "or may be coincident. Check positions with describe()."),
]


def hints_for_error(message):
    """Actionable next steps for an OCCT/toolchain error message."""
    if not message:
        return []
    low = str(message).lower()
    out = []
    for needle, hint in _HINT_TABLE:
        if needle in low and hint not in out:
            out.append(hint)
    return out


def _hint_excepthook(exc_type, exc, tb):
    _ORIG_EXCEPTHOOK(exc_type, exc, tb)
    for h in hints_for_error(f"{exc_type.__name__}: {exc}"):
        print(f"HINT: {h}", flush=True)


_ORIG_EXCEPTHOOK = sys.excepthook
if getattr(_ORIG_EXCEPTHOOK, "__name__", "") != "_hint_excepthook":
    sys.excepthook = _hint_excepthook


# ── Chain edits on an imported STEP (added 2026-09-26) ───────────────────
#
# Thirty of the live chassis scripts import a parent STEP and apply a delta.
# Dependents used to pin the parent by filename; when the chain moved on, the
# dependent either stopped running (its file vanished) or kept passing its
# checks against a parent that no longer existed on the robot. current.json in
# the chain folder names the live parent and records its fingerprint;
# import_current resolves it, and a pinned dependent fails loudly on drift.

import json as _json
from datetime import date as _date
from pathlib import Path as _Path

CURRENT_JSON = "current.json"


def fingerprint(shape_or_block):
    """Compact identity of a solid for chain pinning: exact volume, face and
    edge counts, bbox size. Accepts a Shape/Workplane or a describe() block."""
    blk = shape_or_block if isinstance(shape_or_block, dict) else describe(shape_or_block)
    return {"volume_mm3": blk["volume_mm3"], "faces": blk["faces"],
            "edges": blk["edges"], "bbox_mm": blk["bbox_mm"]}


def fingerprint_matches(a, b, rel_vol=1e-6, bbox_tol=1e-3):
    """True when two fingerprint() blocks describe the same solid: identical
    topology counts, volume within rel_vol, bbox within bbox_tol mm."""
    if a["faces"] != b["faces"] or a["edges"] != b["edges"]:
        return False
    va, vb = a["volume_mm3"], b["volume_mm3"]
    if abs(va - vb) > rel_vol * max(abs(va), abs(vb), 1.0):
        return False
    return all(abs(x - y) <= bbox_tol for x, y in zip(a["bbox_mm"], b["bbox_mm"]))


def set_current(folder, step_file, note=""):
    """Mark step_file as the chain's live part: write folder/current.json with
    its name, today's date, a note (who said so, why) and its fingerprint.
    Call it from the step script right after export_checked, or once by hand
    when the user names the part to print. Returns the record."""
    folder = _Path(folder)
    step = _Path(step_file)
    if not step.is_absolute():
        step = folder / step
    assert step.exists(), f"set_current: {step} does not exist"
    assert step.suffix.lower() in (".step", ".stp"), f"set_current wants a STEP file, got {step.name}"
    shape = cq.importers.importStep(str(step)).val()
    fp = fingerprint(shape)
    rec = {"file": step.name, "set": _date.today().isoformat(), "note": note, "fingerprint": fp}
    (folder / CURRENT_JSON).write_text(_json.dumps(rec, indent=2) + "\n", encoding="utf-8")
    print(f"current.json -> {step.name} (vol {fp['volume_mm3']} mm3, {fp['faces']} faces, "
          f"bbox {fp['bbox_mm']})", flush=True)
    return rec


def read_current(folder):
    """The current.json record of a chain folder, or an AssertionError naming
    what to run if there is none."""
    cj = _Path(folder) / CURRENT_JSON
    assert cj.exists(), (f"{cj} is missing: run cq_helpers.set_current(folder, step_file) "
                         "in the chain folder first (the folder README names the part to print)")
    return _json.loads(cj.read_text(encoding="utf-8"))


def import_current(folder, pin=None):
    """Import the chain's live parent as named by folder/current.json.

    pin: the parent's file stem this script was designed and checked against.
    If the chain has moved to a different part the build FAILS, naming both,
    instead of passing its fit checks against a parent that is no longer on
    the robot. After re-checking against the new parent, move the pin.
    Also fails if the STEP on disk no longer matches the recorded fingerprint
    (the file was replaced without set_current). Returns the Shape."""
    folder = _Path(folder)
    rec = read_current(folder)
    step = folder / rec["file"]
    assert step.exists(), f"current.json names {rec['file']} but it is not in {folder}"
    if pin is not None and step.stem != pin:
        raise AssertionError(
            f"chain drift: this script is pinned to {pin} but {folder.name} is now at "
            f"{step.stem} (set {rec.get('set')}{': ' + rec['note'] if rec.get('note') else ''}). "
            "Re-run every fit check against the new parent, then move the pin.")
    shape = cq.importers.importStep(str(step)).val()
    fp = fingerprint(shape)
    want = rec.get("fingerprint")
    if want:
        assert fingerprint_matches(fp, want), (
            f"{rec['file']} no longer matches its current.json fingerprint "
            f"(file {fp} vs recorded {want}): the STEP was replaced without set_current")
    print(f"import_current: {folder.name} -> {rec['file']} (set {rec.get('set')}"
          f"{', ' + rec['note'] if rec.get('note') else ''})", flush=True)
    return shape


# ── Mesh-path recipes (from the 2026-09-21/22 gotchas, as functions) ─────

def dedupe_points(pts, eps=1e-3):
    """Drop consecutive (cyclic) points closer than eps mm from a closed
    profile. DXF exports repeat a loop's first point just before the closing
    point, up to 3.5e-4 mm off; left in, those slivers collapse to degenerate
    faces in the float32 STL (Organizer Box XL lid, 2026-09-21)."""
    import numpy as np
    p = np.asarray(pts, dtype=float)
    keep = [p[0]]
    for q in p[1:]:
        if np.linalg.norm(q - keep[-1]) >= eps:
            keep.append(q)
    while len(keep) > 3 and np.linalg.norm(keep[-1] - keep[0]) < eps:
        keep.pop()
    return np.array(keep)


def snap_float32(mesh):
    """Rebuild a trimesh through manifold3d at float32 (what the STL stores),
    so sub-micron edges the rounding zeroes are collapsed HERE instead of
    turning into non-manifold edges on STL reload. Returns a processed
    trimesh; asserts it is clean and that every vertex is float32-exact,
    which is the real invariant (2026-09-22)."""
    import numpy as np
    import trimesh
    import manifold3d as m3d
    m = m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
                              tri_verts=np.asarray(mesh.faces, dtype=np.uint32)))
    assert m.status() == m3d.Error.NoError, f"manifold3d rejected the mesh: {m.status()}"
    rm = m.to_mesh()
    out = trimesh.Trimesh(vertices=np.asarray(rm.vert_properties, dtype=np.float64)[:, :3],
                          faces=np.asarray(rm.tri_verts), process=True)
    assert out.is_watertight and out.is_winding_consistent, "float32 rebuild left the mesh unclean"
    assert np.array_equal(out.vertices, out.vertices.astype(np.float32).astype(np.float64)), (
        "vertices are not float32-exact, so the STL write would move (and merge) some")
    return out


def mesh_to_solid(mesh, sew_tol=1e-5):
    """Wrap a clean triangle mesh as an OCCT solid (one planar face per
    triangle) so a mesh-only part can go through export_checked.
    BRepBuilderAPI_MakeShapeOnMesh returns a COMPOUND of faces and silently
    drops zero-area triangles, so the faces are sewn shut (assert 0 free
    edges) rather than stacked into a shell. 36k triangles take about 10 s.
    Export the result with step=False; a STEP of 36k planar faces is not a
    useful file."""
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeShapeOnMesh, BRepBuilderAPI_MakeSolid,
                                    BRepBuilderAPI_Sewing)
    from OCP.BRepLib import BRepLib
    from OCP.gp import gp_Pnt
    from OCP.Poly import Poly_Triangulation, Poly_Triangle
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    tri = Poly_Triangulation(len(mesh.vertices), len(mesh.faces), False)
    for i, p in enumerate(mesh.vertices, 1):
        tri.SetNode(i, gp_Pnt(float(p[0]), float(p[1]), float(p[2])))
    for i, f in enumerate(mesh.faces, 1):
        tri.SetTriangle(i, Poly_Triangle(int(f[0]) + 1, int(f[1]) + 1, int(f[2]) + 1))
    faces = BRepBuilderAPI_MakeShapeOnMesh(tri)
    faces.Build()
    sew = BRepBuilderAPI_Sewing(sew_tol)
    sew.Add(faces.Shape())
    sew.Perform()
    assert sew.NbFreeEdges() == 0, f"{sew.NbFreeEdges()} free edges left after sewing"
    shells = []
    exp = TopExp_Explorer(sew.SewedShape(), TopAbs_SHELL)
    while exp.More():
        shells.append(TopoDS.Shell_s(exp.Current()))
        exp.Next()
    assert len(shells) == 1, f"sewing gave {len(shells)} shells, expected 1"
    solid = BRepBuilderAPI_MakeSolid(shells[0]).Solid()
    BRepLib.OrientClosedSolid_s(solid)
    return cq.Solid(solid)


# ── Printability in the print orientation (2026-10-09, a robot shell's pillar) ──

_UP = {"+z": (0, 0, 1), "-z": (0, 0, -1), "+x": (1, 0, 0), "-x": (-1, 0, 0),
       "+y": (0, 1, 0), "-y": (0, -1, 0)}


def _short_side(poly):
    """Thin side of a shapely polygon's minimum rotated rectangle, mm."""
    import numpy as np
    r = poly.minimum_rotated_rectangle
    if r.geom_type != "Polygon":
        return 0.0
    c = np.asarray(r.exterior.coords)
    return float(min(np.linalg.norm(c[1] - c[0]), np.linalg.norm(c[2] - c[1])))


def islands(part, up="+z", layer=0.2, report=True):
    """Floating islands in a print orientation: material that starts above
    the bed with nothing under it that reaches the plate, so it stands on
    supports (or air) until a later layer ties it into the grounded part.
    part: a cadquery Shape/Workplane, a trimesh mesh, or an STL path. up: the
    model axis pointing away from the bed ("+z" = as modelled). Slices every
    `layer` mm and joins regions layer to layer by overlap, so it sees the
    part the way the printer builds it: a region joined to the rest only
    ABOVE itself is still an island while it prints.
    Returns a list of dicts, tallest first: z0 / z1 (mm above the bed where
    it starts and where it first joins grounded material; z1 None if never),
    height, first_area_mm2, min_area_mm2, min_width_mm (thin side of its
    narrowest layer), slender (height / min_width), risk, and at_xyz (model
    coordinates of its first layer's centroid). risk is a heuristic: HIGH at
    slender >= 3 or height >= 15, watch at slender >= 1.5 or height >= 5.
    Why: a robot shell's wheel-gap pillar started 5.65 above the bed
    (the sled tunnel cut its foot away) and stood 36.8 tall on tree supports,
    6.52 thin front to back, before the arch crowns tied it in. It snapped
    off mid-print (2026-10-09) after every fit gate had passed.
    A shape is meshed as a copy (the caller's stays unmeshed), and an open
    mesh gets export_checked's gentle vertex merge before slicing, so it is
    sliced the way the STL would print (both from a long-nose robot shell,
    2026-10-11)."""
    import os
    import numpy as np
    import trimesh
    if isinstance(part, (str, os.PathLike)):
        mesh = trimesh.load(str(part), force="mesh")
    elif isinstance(part, trimesh.Trimesh):
        mesh = part.copy()
    else:
        # mesh a copy: tessellating in place loosened a long-nose shell's
        # tolerances until isValid() was False and export_checked refused it
        verts, tris = _val(part).copy().tessellate(0.05)
        mesh = trimesh.Trimesh([(v.x, v.y, v.z) for v in verts], tris)
    if not mesh.is_watertight:
        # a hairline crack on a face seam slices to an open loop that never
        # closes into a polygon, so the layers there lose area and what stands
        # on them reads as an island (a false 16.8 tall HIGH one on that shell)
        fixed = _close_cracks(mesh)
        if fixed:
            mesh = fixed[0]
        elif report:
            print("islands: open mesh a gentle vertex merge did not close; cracks can read "
                  "as false islands", flush=True)
    R =trimesh.geometry.align_vectors(_UP[up], (0, 0, 1))
    mesh.apply_transform(R)
    Rinv = np.linalg.inv(R)
    zbed = float(mesh.bounds[0][2])
    n = int(np.ceil((float(mesh.bounds[1][2]) - zbed) / layer))
    paths = mesh.section_multiplane(plane_origin=(0, 0, zbed), plane_normal=(0, 0, 1),
                                    heights=[layer * (k + 0.5) for k in range(n)])
    parent, grounded, rec, done = {}, {}, {}, []

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b, zb):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        ka, kb = rec.pop(ra, None), rec.pop(rb, None)
        parent[rb] = ra
        grounded[ra] = grounded[ra] or grounded[rb]
        if grounded[ra]:
            for r in (ka, kb):
                if r is not None:
                    r["z1"] = zb
                    done.append(r)
        elif ka is None or kb is None:
            if ka or kb:
                rec[ra] = ka or kb
        else:
            first = ka if ka["z0"] <= kb["z0"] else kb
            rec[ra] = dict(first, min_area_mm2=min(ka["min_area_mm2"], kb["min_area_mm2"]),
                           min_width_mm=min(ka["min_width_mm"], kb["min_width_mm"]),
                           last=max(ka["last"], kb["last"]))

    prev = []
    for k, path in enumerate(paths):
        zb = round(layer * k, 6)
        cur = list(path.polygons_full) if path is not None else []
        to3d = path.metadata.get("to_3D", np.eye(4)) if path is not None else None
        for i in range(len(cur)):
            parent[(k, i)] = (k, i)
            grounded[(k, i)] = k == 0
        for i, p in enumerate(cur):
            for j, q in prev:
                if p.intersects(q) and p.intersection(q).area > 1e-6:
                    union((k, i), (k - 1, j), zb)
        by_root = {}
        for i, p in enumerate(cur):
            by_root.setdefault(find((k, i)), []).append(p)
        for root, ps in by_root.items():
            if grounded[root]:
                continue
            area = sum(p.area for p in ps)
            width = min(_short_side(p) for p in ps)
            if root not in rec:
                c = ps[0].centroid
                xyz = Rinv @ (to3d @ np.array([c.x, c.y, 0.0, 1.0]))
                rec[root] = {"z0": zb, "first_area_mm2": round(area, 2), "min_area_mm2": area,
                             "min_width_mm": width, "last": zb,
                             "at_xyz": [round(float(v), 2) for v in xyz[:3]]}
            r = rec[root]
            r["min_area_mm2"] = min(r["min_area_mm2"], area)
            r["min_width_mm"] = min(r["min_width_mm"], width)
            r["last"] = zb
        prev = list(enumerate(cur))
    for r in rec.values():
        r["z1"] = None
        done.append(r)
    out = []
    for r in done:
        top = r["z1"] if r["z1"] is not None else r.pop("last") + layer
        r.pop("last", None)
        h = round(top - r["z0"], 4)
        w = round(r["min_width_mm"], 2)
        s = round(h / w, 2) if w > 0 else float("inf")
        out.append(dict(r, height=h, min_width_mm=w, min_area_mm2=round(r["min_area_mm2"], 2),
                        slender=s, risk="HIGH" if s >= 3 or h >= 15 else
                        ("watch" if s >= 1.5 or h >= 5 else "low")))
    out.sort(key=lambda r: -r["height"])
    if report:
        print(f"islands (up {up}, layer {layer}): {len(out)}", flush=True)
        for r in out:
            print(f"  {r['risk']:5s} {r['height']:6.2f} tall from bed+{r['z0']:.2f} to "
                  f"{'never' if r['z1'] is None else 'bed+%.2f' % r['z1']}, thin side "
                  f"{r['min_width_mm']:.2f}, first layer {r['first_area_mm2']:.1f} mm2, "
                  f"at {r['at_xyz']}", flush=True)
    return out


# ── Engraved letters (from pocket labels and L/R marks) ──

def glyph(ch, size, depth, font="Arial", font_path=None):
    """One character as a Shape extruded +z from z = 0 by depth, centred on
    its INK box, not the font's advance box (the advance box is a fraction
    wider, and at label sizes that fraction is the fit margin). Name the
    font_path explicitly for anything that must not silently substitute:
    r"C:\\Windows\\Fonts\\impact.ttf", r"C:\\Windows\\Fonts\\arial.ttf"."""
    kw = dict(font=font, kind="regular", halign="center", valign="center", combine=False)
    if font_path:
        kw["fontPath"] = font_path
    g = cq.Workplane("XY").text(ch, size, depth, **kw).val()
    b = g.BoundingBox()
    return g.translate((-(b.xmin + b.xmax) / 2.0, -(b.ymin + b.ymax) / 2.0, 0.0))


def fit_text_size(chars, win_w, win_h, depth=1.0, font="Arial", font_path=None,
                  slack=0.10, probe=10.0):
    """ONE font size at which every character's ink box fits a win_w x win_h
    window (mm) less slack, so a set of marks (R and L) come out the same
    height. Solved at a probe size and scaled, since ink scales linearly.
    Returns (size, cap_height_mm). Assert the cap height against a minimum
    afterwards: a wider substituted font solves to a shorter letter."""
    sizes = []
    for ch in chars:
        b = glyph(ch, probe, depth, font, font_path).BoundingBox()
        sizes.append(probe * min((win_w - slack) / b.xlen, (win_h - slack) / b.ylen))
    size = min(sizes)
    cap_h = max(glyph(ch, size, depth, font, font_path).BoundingBox().ylen for ch in chars)
    return size, cap_h
