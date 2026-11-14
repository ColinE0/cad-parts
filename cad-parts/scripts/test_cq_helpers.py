# Copyright 2026 Colin Ezra Wilder. SPDX-License-Identifier: Apache-2.0
"""Self-test for cq_helpers (venv site-packages). 2026-09-26.

Plain asserts, no pytest (not in the venv). Run it the way every build runs:

    & "$env:USERPROFILE\\.claude\\skills\\cad-parts\\scripts\\run_watchdogged.ps1" `
        -Script "$env:USERPROFILE\\.claude\\skills\\cad-parts\\scripts\\test_cq_helpers.py" -Tail 30

Everything it writes goes to a fresh temp folder, deleted at the end. Ends with DONE.
Run it after ANY edit to cq_helpers.py: export_checked is the gate that already
caught a shipped bad part, and this is the only thing standing between an edit and a silent
break. Group 9 also checks that the skill's versioned copies in ../venv-modules match what is
installed in site-packages. Group 11 renders offscreen through VTK (a few seconds), render6,
render_compare and render_views. Group 12 checks export_checked's mesh= pin.
Set CADPARTS_SKIP_RENDER=1 to skip group 11 where there is no OpenGL 3.2 (the CI runner).
"""
import os
import shutil
import tempfile
import time
from pathlib import Path

import cadquery as cq
import cq_helpers as h

TMP = Path(tempfile.mkdtemp(prefix="cq_helpers_test_"))
print(f"temp folder {TMP}", flush=True)
try:
    # 1. export gate on a clean cube ------------------------------------------------
    cube = cq.Workplane("XY").box(10, 10, 10)
    m = h.export_checked(cube, str(TMP / "cube"))
    assert (TMP / "cube.step").exists() and (TMP / "cube.stl").exists()
    assert m.is_watertight and abs(m.volume - 1000.0) < 1e-3
    d0 = h.describe(cube)
    assert d0["bbox_mm"] == [10.0, 10.0, 10.0] and abs(d0["volume_mm3"] - 1000.0) < 1e-6
    assert d0["faces"] == 6 and d0["edges"] == 12 and d0["vertices"] == 8
    m2 = h.export_checked(cube, str(TMP / "cube2"), stl_dir="stl")
    assert (TMP / "cube2.step").exists() and (TMP / "stl" / "cube2.stl").exists()
    assert not (TMP / "cube2.stl").exists() and m2.is_watertight
    # the STL is written from a copy, so the caller's shape stays unmeshed, as islands() does
    # (meshing in place turned a long-nose shell invalid, 2026-10-11)
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location

    def unmeshed(wp):
        return all(BRep_Tool.Triangulation_s(fc.wrapped, TopLoc_Location()) is None
                   for fc in h._val(wp).Faces())

    bare = cq.Workplane("XY").box(1, 1, 1)
    cq.exporters.export(bare, str(TMP / "bare.stl"))
    assert not unmeshed(bare), "positive control: CadQuery's STL export meshes the shape it writes"
    assert unmeshed(cube), "export_checked meshed the caller's shape in place"
    print("1 export_checked + describe ok (stl_dir too; cube left unmeshed)", flush=True)

    # 2. diff / is_noop ----------------------------------------------------------------
    same = h.diff(d0, h.describe(cube.translate((0, 0, 0))))
    assert h.is_noop(same)
    holed = cube.faces(">Z").workplane().hole(3.0)
    dh = h.diff(d0, h.describe(holed))
    assert not h.is_noop(dh) and dh["volume_delta_mm3"] < 0 and dh["faces_delta"] == 1
    moved = h.diff(d0, h.describe(cube.translate((5, 0, 0))))
    assert not h.is_noop(moved), "a pure translate must not read as a no-op"
    print("2 diff / is_noop ok", flush=True)

    # 3. interference ---------------------------------------------------------------
    other = cq.Workplane("XY").box(10, 10, 10).translate((9, 9, 9))
    inter = h.interference(cube, other)
    assert inter["intersects"] and abs(inter["volume_mm3"] - 1.0) < 1e-6
    far = cq.Workplane("XY").box(10, 10, 10).translate((30, 0, 0))
    clr = h.interference(cube, far, clearance=True)
    assert not clr["intersects"] and abs(clr["clearance_mm"] - 20.0) < 0.05
    # dense mesh vs small part: the clearance path must stay memory-bounded and exact
    # (2026-09-26: a step 10c plate vs sled query asked trimesh for a 12 M row array)
    dense = cq.Workplane("XY").sphere(30.0)
    pin = cq.Workplane("XY").box(2, 2, 2).translate((35.0, 0, 0))   # 4 mm off the sphere
    t0 = time.time()
    r = h.interference(dense, pin, clearance=True, tol=0.02)
    assert not r["intersects"] and abs(r["clearance_mm"] - 4.0) < 0.05, r
    # the clearance path meshes copies, so the caller's shapes stay unmeshed, as islands() does
    # (meshing in place turned a long-nose shell invalid, 2026-10-11). cube too: group 1
    # checked export_checked left it unmeshed.
    probe = cq.Workplane("XY").box(1, 1, 1)
    probe.val().tessellate(0.3)
    assert not unmeshed(probe), "positive control: tessellate() meshes the shape it is called on"
    assert unmeshed(cube) and unmeshed(far) and unmeshed(dense) and unmeshed(pin), \
        "interference(clearance=True) meshed the caller's shapes in place"
    print(f"3 interference ok (dense clearance {r['clearance_mm']} mm in {time.time() - t0:.1f} s; "
          "inputs left unmeshed)", flush=True)

    # 4. chain pointer: set_current / import_current / pin / fingerprint -------------
    chain = TMP / "chain"
    chain.mkdir()
    shutil.copy(TMP / "cube.step", chain / "plate_step1.step")
    rec = h.set_current(chain, "plate_step1.step", note="test")
    assert (chain / h.CURRENT_JSON).exists() and rec["file"] == "plate_step1.step"
    got = h.import_current(chain)
    assert h.fingerprint_matches(h.fingerprint(got), rec["fingerprint"])
    got2 = h.import_current(chain, pin="plate_step1")
    assert abs(got2.Volume() - 1000.0) < 1e-3
    try:
        h.import_current(chain, pin="plate_step0")
        raise SystemExit("pin mismatch did not raise")
    except AssertionError as e:
        assert "chain drift" in str(e) and "plate_step0" in str(e) and "plate_step1" in str(e)
    # replace the STEP behind the pointer's back: the fingerprint must catch it
    h.export_checked(holed, str(chain / "plate_step1"), stl=False)
    try:
        h.import_current(chain)
        raise SystemExit("fingerprint mismatch did not raise")
    except AssertionError as e:
        assert "fingerprint" in str(e)
    try:
        h.import_current(TMP)   # no current.json here
        raise SystemExit("missing current.json did not raise")
    except AssertionError as e:
        assert "set_current" in str(e)
    print("4 set_current / import_current / pin / fingerprint ok", flush=True)

    # 5. mesh-path recipes ------------------------------------------------------------
    import numpy as np
    import trimesh
    loop = np.array([[0, 0], [10, 0], [10, 10], [0, 10], [0.0002, 0.0001]])
    dd = h.dedupe_points(loop, eps=1e-3)
    assert len(dd) == 4, f"dedupe left {len(dd)} points"
    box = trimesh.creation.box(extents=(10.0, 6.0, 4.0))
    snapped = h.snap_float32(box)
    assert snapped.is_watertight and abs(snapped.volume - 240.0) < 1e-3
    solid = h.mesh_to_solid(snapped)
    assert solid.isValid() and abs(solid.Volume() - 240.0) < 1e-3
    h.export_checked(solid, str(TMP / "from_mesh"), step=False)
    # and the gate itself: a cracked mesh is NOT watertight (what export_checked refuses)
    cracked = trimesh.Trimesh(vertices=box.vertices, faces=box.faces[1:], process=False)
    assert not cracked.is_watertight
    print("5 dedupe_points / snap_float32 / mesh_to_solid ok", flush=True)

    # 6. letters ----------------------------------------------------------------------
    size, cap_h = h.fit_text_size("RL", 6.5, 11.0, depth=1.0, font="Arial",
                                  font_path=r"C:\Windows\Fonts\arial.ttf")
    assert size > 0 and cap_h <= 11.0
    for ch in "RL":
        b = h.glyph(ch, size, 1.0, "Arial", r"C:\Windows\Fonts\arial.ttf").BoundingBox()
        assert b.xlen <= 6.5 + 1e-6 and b.ylen <= 11.0 + 1e-6, f"{ch} runs out of the window"
        assert abs(b.xmin + b.xmax) < 1e-6 and abs(b.ymin + b.ymax) < 1e-6, f"{ch} not ink-centred"
        assert abs(b.zmin) < 1e-6 and abs(b.zmax - 1.0) < 1e-3
    print(f"6 glyph / fit_text_size ok (size {size:.3f}, cap {cap_h:.2f} mm)", flush=True)

    # 7. hints ------------------------------------------------------------------------
    assert h.hints_for_error("BRep_API: command not done")
    assert h.hints_for_error("") == []
    print("7 hints ok", flush=True)

    # (group 8 tested a robot-frame module that is not part of this edition)

    # 9. the skill's versioned copy matches what is installed ---------------------------
    SKILL_MODS = Path(__file__).resolve().parent.parent / "venv-modules"
    for mod in (h,):
        installed = Path(mod.__file__)
        copy = SKILL_MODS / installed.name
        assert copy.exists(), f"{copy} missing: copy {installed} there"
        a = copy.read_text(encoding="utf-8").replace("\r\n", "\n")
        b = installed.read_text(encoding="utf-8").replace("\r\n", "\n")
        assert a == b, (f"{installed.name} differs between site-packages and the skill's "
                        "venv-modules copy: update one from the other")
    print("9 venv-modules copies match site-packages", flush=True)

    # 10. islands: a pendant hanging from an arch's beam stands on air until the beam ties it in
    legs = (cq.Workplane("XY").box(4, 10, 20, centered=(True, True, False)).translate((-10, 0, 0))
            .union(cq.Workplane("XY").box(4, 10, 20, centered=(True, True, False)).translate((10, 0, 0))))
    arch = legs.union(cq.Workplane("XY").box(24, 10, 4, centered=(True, True, False)).translate((0, 0, 20)))
    pend = arch.union(cq.Workplane("XY").box(3, 3, 12, centered=(True, True, False)).translate((0, 0, 8)))
    found = h.islands(pend, up="+z")
    # the caller's shape is left unmeshed and valid: islands() meshing it in place turned a
    # long-nose shell invalid, so export_checked refused it (2026-10-11)
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    pv = pend.val()
    assert pv.isValid(), "islands() left the caller's shape invalid"
    assert all(BRep_Tool.Triangulation_s(fc.wrapped, TopLoc_Location()) is None for fc in pv.Faces()), \
        "islands() meshed the caller's shape in place"

    def pendant_ok(found):
        assert len(found) == 1, found
        f = found[0]
        assert abs(f["z0"] - 8.0) < 1e-6 and abs(f["z1"] - 20.0) < 1e-6 and abs(f["height"] - 12.0) < 1e-6, f
        assert abs(f["min_width_mm"] - 3.0) < 0.01 and f["risk"] == "HIGH", f
        assert abs(f["at_xyz"][0]) < 0.01 and abs(f["at_xyz"][1]) < 0.01 and abs(f["at_xyz"][2] - 8.1) < 0.01, f

    pendant_ok(found)
    assert h.islands(pend, up="-z", report=False) == [], "flipped, the beam is on the bed: no islands"
    assert h.islands(arch, up="+z", report=False) == [], "the bare arch has no islands"

    # hairline seam cracks: islands() slices the mesh merged the way export_checked writes it.
    # A crack's open loop never closes into a polygon, so its layers lose that area: on a
    # long-nose shell that made a false 16.8 tall HIGH island (2026-10-11).
    def tmesh(wp):
        verts, tris = wp.val().copy().tessellate(0.05)
        return trimesh.Trimesh([(v.x, v.y, v.z) for v in verts], tris)

    def crack(m, sel, y):
        """m with the faces in sel given their own copies of their vertices at y, 3e-5 further
        along y: a hairline crack down that one seam (a whole face cut loose instead leaves
        quad holes that fill_holes patches into a zero-area pillow, not what a seam does)."""
        V, Fc = m.vertices.copy(), m.faces.copy()
        idx = np.unique(Fc[sel])
        idx = idx[np.abs(V[idx, 1] - y) < 1e-6]
        lut = np.arange(len(V))
        lut[idx] = len(V) + np.arange(len(idx))
        Fc[sel] = lut[Fc[sel]]
        return trimesh.Trimesh(np.vstack([V, V[idx] + (0.0, 3e-5, 0.0)]), Fc, process=False)

    def polys_at(m, z):
        p = m.section_multiplane(plane_origin=(0, 0, 0), plane_normal=(0, 0, 1), heights=[z])[0]
        return 0 if p is None else len(p.polygons_full)

    # a column of two stacked boxes, unmerged so its walls split at z 10, cracked down the lower
    # +x wall's +y corner: sliced raw the lower half is gone and the upper half stands on air.
    # No island once merged.
    col = (cq.Workplane("XY").box(10, 10, 10, centered=(True, True, False))
           .union(cq.Workplane("XY").box(10, 10, 10, centered=(True, True, False)).translate((0, 0, 10)),
                  clean=False))
    cm = tmesh(col)
    c = cm.triangles_center
    cc = crack(cm, (np.abs(c[:, 0] - 5.0) < 1e-6) & (c[:, 2] < 10.0), 5.0)
    assert cm.is_watertight and not cc.is_watertight
    assert polys_at(cc, 5.0) == 0 and polys_at(cc, 15.0) == 1, "positive control: the crack opens the lower loop"
    assert h.islands(cc, report=False) == [], "a seam crack read as an island"
    # and a real island survives the merge, even with its own corner cracked (raw, the crack hides it)
    pm = tmesh(pend)
    c = pm.triangles_center
    pc = crack(pm, (np.abs(c[:, 0] - 1.5) < 1e-6) & (c[:, 2] > 8.0) & (c[:, 2] < 20.0), 1.5)
    assert not pc.is_watertight and polys_at(pc, 14.0) == 2 and polys_at(pm, 14.0) == 3
    pendant_ok(h.islands(pc, report=False))
    print("10 islands ok (caller's shape unmeshed and valid; seam cracks merged, the real island kept)",
          flush=True)

    # 11. renders are depth-buffered: a red plate in front of a finely meshed green sphere hides it.
    # matplotlib's painter sort (render6 until 2026-10-09) ordered whole triangles by mean depth,
    # so small far triangles painted over long near ones: green PCB streaks through a red lid
    # that measured 0.000 mm3 of contact. The plate leans back (y rises with z) so its long
    # triangles' centroids sit BEHIND the sphere while the plate still covers it: the old
    # renderer showed the sphere through it here.
    if os.environ.get("CADPARTS_SKIP_RENDER") == "1":
        # set on machines without OpenGL 3.2 (VTK needs it), e.g. GitHub's Windows runners
        print("11 renders SKIPPED (CADPARTS_SKIP_RENDER=1)", flush=True)
    else:
        plate = (cq.Workplane("XY").box(40, 2, 300).rotate((0, 0, 0), (1, 0, 0), -24.2)
                 .translate((0, -16, 0)))
        ball = cq.Workplane("XY").sphere(10.0)
        assert not h.interference(plate, ball)["intersects"]
        items = [(h._shape_tris(plate, 0.1), (0.8, 0.1, 0.1)), (h._shape_tris(ball, 0.05), (0.1, 0.8, 0.1))]
        assert len(items[1][0]) > 20 * len(items[0][0]), "the sphere must be the finely meshed part"
        assert unmeshed(plate) and unmeshed(ball), "_shape_tris meshed the caller's shape in place"
        front, back = h._render_views(items, [(0, -90), (0, 90)], (320, 240))
        assert front.shape == (240, 320, 3) and front.dtype == np.uint8

        def green(img):
            g = img.astype(int)
            return int(((g[..., 1] > g[..., 0] + 60) & (g[..., 1] > g[..., 2] + 60)).sum())

        def red(img):
            g = img.astype(int)
            return int(((g[..., 0] > g[..., 1] + 60) & (g[..., 0] > g[..., 2] + 60)).sum())

        assert green(front) == 0 and red(front) > 3000, (green(front), red(front))
        assert green(back) > 100, "positive control: from behind the sphere is in view"
        two = cq.Workplane("XY").add([cube.val(), far.val()])
        assert len(h._shape_tris(two, 0.3)) == 24, "a multi-object Workplane renders every object"
        # the compound shares cube's and far's faces: meshing it uncopied would mesh both
        assert unmeshed(cube) and unmeshed(far), \
            "_shape_tris meshed a shape on a multi-object Workplane's stack in place"
        import matplotlib.pyplot as plt
        h.render6(cube, str(TMP / "cube.png"))
        assert plt.imread(str(TMP / "cube.png")).shape[:2] == (1040, 1800)
        assert unmeshed(cube), "render6 meshed the caller's shape in place"
        plt.imsave(str(TMP / "ref.png"), np.zeros((40, 60, 3)))
        h.render_compare(cube, str(TMP / "ref.png"), str(TMP / "cmp.png"))
        assert (TMP / "cmp.png").exists()
        assert unmeshed(cube), "render_compare meshed the caller's shape in place"

        # render_views, the public multi-colour form: the same plate-over-sphere scene, one item
        # as a Shape with its own tol, one as pre-tessellated triangles. No labels, title or
        # legend, so the PNG is exactly the two views side by side.
        def png(name):
            return (plt.imread(str(TMP / name))[..., :3] * 255).round().astype(np.uint8)

        h.render_views([(plate, (0.8, 0.1, 0.1), 0.1), (items[1][0], "#1acc1a")], str(TMP / "views.png"),
                       [("", 0, -90), ("", 0, 90)], size=(320, 240))
        vw = png("views.png")
        assert vw.shape == (240, 640, 3), vw.shape
        assert green(vw[:, :320]) == 0 and red(vw[:, :320]) > 3000, (green(vw[:, :320]), red(vw[:, :320]))
        assert green(vw[:, 320:]) > 100, "positive control: from behind the sphere is in view"
        assert vw[0, 0].min() > 250, "default background is white"
        # frame: framed on the first cube's box, the cube 20 mm away is out of the picture
        pair = [(cube, "red"), (far, "#1acc1a")]
        h.render_views(pair, str(TMP / "pair.png"), [("", 0, -90)], size=(320, 240))
        h.render_views(pair, str(TMP / "close.png"), [("", 0, -90)], size=(320, 240), frame=(-5, 5, -5, 5, -5, 5))
        assert green(png("pair.png")) > 1000 and green(png("close.png")) == 0
        assert red(png("close.png")) > 4 * red(png("pair.png")), "the close-up is not framed on the box"
        # labels, title and legend add their strips around the views
        h.render_views(pair, str(TMP / "sheet.png"), [("front", 0, -90), ("top", 90, -90), ("iso", 30, -60)],
                       title="t", size=(200, 150), cols=2, legend=[("red", "cube"), ("#1acc1a", "far")])
        assert png("sheet.png").shape[:2] == (50 + 2 * (34 + 150) + 44, 400)
        assert unmeshed(plate) and unmeshed(far), "render_views meshed the caller's shapes in place"
        print("11 renders ok (depth-buffered: 0 hidden px through the plate; render_views too; "
              "shapes left unmeshed)", flush=True)

    # 12. export_checked(mesh=(deflection, angular)). The STL is written from a fresh copy, so a
    # mesh the caller pinned on its own shape never reaches it: the 2026-10-12 D3.4 plain hub cheek
    # failed the gate that way (its vendor sliver faces leak at anything but 0.05 / 0.2 absolute).
    # mesh= pins it on the copy instead, byte for byte the hub-cheek scripts' own pinned write.
    import contextlib
    import io
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    cyl = cq.Workplane("XY").cylinder(10.0, 8.0).faces(">Z").edges().fillet(1.0)
    ref = cyl.val().copy()      # hub_cheek_sockets_d34.py's export_stl_pinned, on a copy
    BRepTools.Clean_s(ref.wrapped)
    ref.exportStl(str(TMP / "cyl_ref.stl"), tolerance=0.05, angularTolerance=0.2, relative=False,
                  parallel=False)
    mp = h.export_checked(cyl, str(TMP / "cyl_pinned"), step=False, mesh=(0.05, 0.2))
    assert (TMP / "cyl_pinned.stl").read_bytes() == (TMP / "cyl_ref.stl").read_bytes(), \
        "mesh=(0.05, 0.2) did not write the pinned STL"
    md = h.export_checked(cyl, str(TMP / "cyl_default"), step=False)
    assert len(md.faces) != len(mp.faces), "positive control: the default mesh is not the pinned one"
    assert unmeshed(cyl), "export_checked(mesh=...) meshed the caller's shape in place"
    # the old recipe (pin the mesh on the shape, then export) loses it, and now says so
    BRepTools.Clean_s(cyl.val().wrapped)
    BRepMesh_IncrementalMesh(cyl.val().wrapped, 0.05, False, 0.2, False)
    assert not unmeshed(cyl)
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        h.export_checked(cyl, str(TMP / "cyl_premeshed"), step=False)
    assert (TMP / "cyl_premeshed.stl").read_bytes() == (TMP / "cyl_default.stl").read_bytes(), \
        "a mesh pinned on the caller's shape reached the STL: the copy was not meshed fresh"
    assert "pass mesh=(deflection, angular)" in log.getvalue(), "no note about the dropped mesh"
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        h.export_checked(cube, str(TMP / "cube3"), step=False)
    assert "export_checked note" not in log.getvalue(), "the dropped-mesh note fired on an unmeshed shape"
    try:
        h.export_checked(cube, str(TMP / "cube4"), step=False, mesh=(0.0, 0.2))
        raise SystemExit("mesh=(0, 0.2) did not raise")
    except AssertionError as e:
        assert "deflection" in str(e)
    print(f"12 export_checked mesh= ok (pinned STL byte-identical, {len(mp.faces)} faces vs "
          f"{len(md.faces)} default; caller unmeshed; a pre-pinned mesh is dropped with a note)", flush=True)
finally:
    shutil.rmtree(TMP, ignore_errors=True)
print("DONE", flush=True)
