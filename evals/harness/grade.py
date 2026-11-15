"""Grades every finished cad-parts eval run: geometry of the parts each run produced, plus process
facts read from its transcript. Writes grades.json and prints one block per run.

Run it through the cad-parts runner with the eval venv (it imports STEP files). The island checks
(evals 8, 10, 12) import cq_helpers from the skill-under-test copy; evals 10 to 12 also import
their project's reference module (chassis_ref.py, scout_refs.py) or plates from the spec's
eval-assets.

A run's outputs are every file it created plus every input it changed: evals 10 to 12 attach whole
folders, and a run may rebuild a part in place.
"""
import ast
import hashlib
import importlib.util
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

import cadquery as cq
import numpy as np
import trimesh
from OCP.BRepAdaptor import BRepAdaptor_Surface

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "spec" if (ROOT / "spec" / "evals.json").exists() else ROOT
HOME = str(Path.home()).lower()
TEMP = str(Path.home() / "AppData" / "Local" / "Temp").lower()
RUNS = ROOT / "runs"
LOGS = ROOT / "logs"
SKILL = (ROOT / "skill-under-test" / "cad-parts").resolve()
VENV = (ROOT / "venv").resolve()
EVALS = {e["id"]: e for e in json.loads((SPEC / "evals.json").read_text(encoding="utf-8"))["evals"]}

# Intended parts: sorted bbox extents (mm) and volume (mm3).
TARGET = {
    1: ([9.0, 9.0, 12.0], math.pi / 4 * (9.0 ** 2 - 4.3 ** 2) * 12.0),
    2: ([5.0, 5.0, 14.0], math.pi / 4 * (5.0 ** 2 - 2.4 ** 2) * 14.0),
    3: ([8.0, 12.0, 20.0], 20.0 * 12.0 * 8.0),
    5: ([25.0, 30.0, 40.0], 40 * 25 * 4 + 4 * 25 * 26 - 2 * math.pi * 2.2 ** 2 * 4),
}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def input_files(ev):
    """Every input file of an eval, as a posix path relative to the spec; a folder entry stands for
    every file under it."""
    out = []
    for f in ev["files"]:
        src = SPEC / f
        if src.is_dir():
            out += sorted(p.relative_to(SPEC).as_posix() for p in src.rglob("*") if p.is_file())
        else:
            out.append(Path(f).as_posix())
    return out


def spec_module(rel, name):
    """A project's reference module (chassis_ref.py, scout_refs.py) imported from the spec copy."""
    spec = importlib.util.spec_from_file_location(name, SPEC / "eval-assets" / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def skill_helpers():
    """The skill-under-test's cq_helpers (its island check)."""
    if str(SKILL / "venv-modules") not in sys.path:
        sys.path.insert(0, str(SKILL / "venv-modules"))
    import cq_helpers  # noqa: PLC0415
    return cq_helpers


def check_stl(p):
    m = trimesh.load(str(p), force="mesh")
    ext = sorted(float(x) for x in m.extents)
    return {"file": p.name, "watertight": bool(m.is_watertight), "winding": bool(m.is_winding_consistent),
            "extents": [round(x, 3) for x in ext], "volume": round(float(m.volume), 2) if m.is_watertight else None,
            "faces": len(m.faces)}


def step_solid(p):
    wp = cq.importers.importStep(str(p))
    vals = [v for v in wp.vals() if isinstance(v, cq.Shape)]
    return vals[0] if len(vals) == 1 else cq.Compound.makeCompound(vals)


def check_step(p):
    s = step_solid(p)
    bb = s.BoundingBox()
    ext = sorted([bb.xlen, bb.ylen, bb.zlen])
    cyl = sorted({round(BRepAdaptor_Surface(f.wrapped).Cylinder().Radius() * 2, 3)
                  for f in s.Faces() if f.geomType() == "CYLINDER"})
    return {"file": p.name, "valid": bool(s.isValid()), "solids": len(s.Solids()),
            "extents": [round(x, 3) for x in ext], "volume": round(s.Volume(), 2), "cyl_diameters": cyl}


def matches(rec, eid, tol=0.02, vtol=0.01):
    if eid not in TARGET or rec is None:
        return None
    ext, vol = TARGET[eid]
    ok = all(abs(a - b) <= tol for a, b in zip(rec["extents"], ext))
    if rec.get("volume") is not None:
        ok = ok and abs(rec["volume"] - vol) <= vtol * vol
    return ok


def holes_xy(shape, axis=(0, 0, 1)):
    """Centres (x, y) and diameters of cylinder faces whose axis is along z."""
    out = []
    for f in shape.Faces():
        if f.geomType() != "CYLINDER":
            continue
        c = BRepAdaptor_Surface(f.wrapped).Cylinder()
        d = c.Axis().Direction()
        if abs(abs(d.Z()) - 1) > 1e-6:
            continue
        loc = c.Location()
        out.append((round(loc.X(), 3), round(loc.Y(), 3), round(c.Radius() * 2, 3)))
    return sorted(set(out))


def eval4_fit(run):
    """Bracket vs plate in the plate's own frame: seated height, overlap, hole axes shared."""
    plate = step_solid(SPEC / "eval-assets" / "plate-chain" / "plate_step1.step")
    pbb = plate.BoundingBox()
    plate_holes = holes_xy(plate)
    res = []
    for p in sorted(run.rglob("*.step")):
        if "eval-assets" in p.parts:
            continue
        try:
            s = step_solid(p)
        except Exception as e:  # noqa: BLE001
            res.append({"file": p.name, "error": str(e)[:120]})
            continue
        bb = s.BoundingBox()
        if len(s.Solids()) > 1 and abs(s.Volume() - plate.Volume()) < 1:  # an assembly file
            continue
        try:
            overlap = s.intersect(plate).Volume()
        except Exception:  # noqa: BLE001
            overlap = None
        bh = holes_xy(s)
        shared = [h for h in bh if any(math.hypot(h[0] - q[0], h[1] - q[1]) < 0.05 for q in plate_holes)]
        res.append({"file": p.name, "solids": len(s.Solids()), "top_above_plate": round(bb.zmax - pbb.zmax, 3),
                    "zmin_minus_plate_top": round(bb.zmin - pbb.zmax, 3),
                    "overlap_mm3": None if overlap is None else round(overlap, 3),
                    "holes_on_plate_axes": len(shared), "hole_diams": sorted({h[2] for h in shared})})
    return {"plate_top_z": round(pbb.zmax, 3), "plate_holes": plate_holes, "candidates": res}


def new_steps(files):
    return [p for p in files if p.suffix.lower() in (".step", ".stp")]


def eval7_check(files):
    """Puck stretched 1.2x in X: every STL against the target (unsorted extents, so the axis counts),
    every STEP's face types (a B-rep non-uniform scale turns every face into a B-spline)."""
    src = step_solid(SPEC / "eval-assets" / "puck.step")
    v0 = src.Volume(tol=1e-7)
    want, vwant = [36.0, 30.0, 10.0], 1.2 * v0
    stl, step = [], []
    for p in files:
        if p.suffix.lower() != ".stl":
            continue
        m = trimesh.load(str(p), force="mesh")
        ext = [round(float(x), 3) for x in m.extents]
        vol = float(m.volume) if m.is_watertight else None
        ok = bool(m.is_watertight) and all(abs(a - b) <= 0.1 for a, b in zip(ext, want)) \
            and vol is not None and abs(vol - vwant) <= 0.01 * vwant
        stl.append({"file": p.name, "ok": ok, "watertight": bool(m.is_watertight), "extents_xyz": ext,
                    "volume": None if vol is None else round(vol, 2), "faces": len(m.faces)})
    for p in new_steps(files):
        s = step_solid(p)
        bb = s.BoundingBox()
        ext = [round(bb.xlen, 3), round(bb.ylen, 3), round(bb.zlen, 3)]
        kinds = Counter(f.geomType() for f in s.Faces())
        step.append({"file": p.name, "stretched": all(abs(a - b) <= 0.1 for a, b in zip(ext, want)),
                     "faces": len(s.Faces()), "bspline_share": round(kinds.get("BSPLINE", 0) / max(len(s.Faces()), 1), 3),
                     "volume": round(s.Volume(tol=1e-7), 2), "extents_xyz": ext})
    return {"target_volume": round(vwant, 2), "stl": stl, "step": step,
            "stl_ok": [s["file"] for s in stl if s["ok"]],
            "brep_scaled_steps": [s["file"] for s in step if s["stretched"] and s["bspline_share"] == 1.0]}


def eval8_check(files):
    """Sled bridge with a tunnel: every bridge-sized STEP gets the sled envelope (12 x 8 along y, on
    its bed face, centred in x) intersected against it and an island check printed upright (+z)."""
    sys.path.insert(0, str(SKILL / "venv-modules"))
    import cq_helpers as H  # noqa: PLC0415  (the skill's own island check)
    out = []
    for p in new_steps(files):
        s = step_solid(p)
        bb = s.BoundingBox()
        if not all(abs(a - b) < 0.5 for a, b in zip(sorted([bb.xlen, bb.ylen, bb.zlen]), [32, 40, 80])):
            continue
        cx = (bb.xmin + bb.xmax) / 2
        sled = cq.Solid.makeBox(12, 400, 8, cq.Vector(cx - 6, (bb.ymin + bb.ymax) / 2 - 200, bb.zmin))
        overlap = s.intersect(sled).Volume()
        isl = H.islands(s, up="+z", report=False)
        high = [i for i in isl if i["risk"] == "HIGH"]
        out.append({"file": p.name, "mtime": p.stat().st_mtime, "solids": len(s.Solids()),
                    "sled_overlap_mm3": round(overlap, 3), "sled_clear": overlap < 0.01,
                    "islands": len(isl), "high": len(high),
                    "tallest": None if not isl else {k: isl[0][k] for k in ("z0", "z1", "height", "min_width_mm", "risk")}})
    tunnel = sorted((c for c in out if c["sled_clear"]), key=lambda c: c["mtime"])
    return {"candidates": out, "tunnel_parts": len(tunnel),
            "latest_tunnel_part": None if not tunnel else tunnel[-1]["file"],
            "latest_high_islands": None if not tunnel else tunnel[-1]["high"]}


def fit_vs(s, plate):
    pbb, bb = plate.BoundingBox(), s.BoundingBox()
    try:
        overlap = s.intersect(plate).Volume()
    except Exception:  # noqa: BLE001
        overlap = None
    ph = holes_xy(plate)
    shared = [q for q in holes_xy(s) if any(math.hypot(q[0] - r[0], q[1] - r[1]) < 0.05 for r in ph)]
    f = {"seat_gap": round(bb.zmin - pbb.zmax, 3), "proud": round(bb.zmax - pbb.zmax, 3),
         "overlap_mm3": None if overlap is None else round(overlap, 3), "holes_on_axes": len(shared)}
    f["fits"] = abs(f["seat_gap"]) < 0.01 and overlap is not None and overlap < 0.01 \
        and f["holes_on_axes"] >= 2 and abs(f["proud"] - 15) < 0.05
    return f


def eval9_check(files):
    """Bracket vs both plates of the moved chain: which parent does each delivered bracket fit?"""
    chain = SPEC / "eval-assets" / "plate-chain-moved"
    p1, p2 = step_solid(chain / "plate_step1.step"), step_solid(chain / "plate_step2.step")
    out = []
    for p in new_steps(files):
        try:
            s = step_solid(p)
        except Exception as e:  # noqa: BLE001
            out.append({"file": p.name, "error": str(e)[:120]})
            continue
        if len(s.Solids()) != 1 or any(abs(s.Volume() - q.Volume()) < 1 for q in (p1, p2)):
            continue  # a plate, or an assembly with one in it
        f1, f2 = fit_vs(s, p1), fit_vs(s, p2)
        out.append({"file": p.name, "mtime": p.stat().st_mtime, "step1": f1, "step2": f2})
    good = [c for c in out if "step2" in c]
    latest = max(good, key=lambda c: c["mtime"]) if good else None
    return {"candidates": out,
            "fits_step2": [c["file"] for c in good if c["step2"]["fits"]],
            "fits_step1_only": [c["file"] for c in good if c["step1"]["fits"] and not c["step2"]["fits"]],
            "latest": None if latest is None else
            {"file": latest["file"], "fits_step1": latest["step1"]["fits"], "fits_step2": latest["step2"]["fits"]}}


def tallest(isl):
    return None if not isl else {k: isl[0][k] for k in ("z0", "z1", "height", "min_width_mm", "risk")}


def wall_gap(s, x, z, half=80.0):
    """Width (y) of the opening round y = 0 in a wall at x, on a 0.2 mm band at height z; 0 when
    the wall is solid at y = 0."""
    band = s.intersect(cq.Solid.makeBox(2.0, 2 * half, 0.2, cq.Vector(x - 1.0, -half, z - 0.1)))
    ivs = [(b.BoundingBox().ymin, b.BoundingBox().ymax) for b in band.Solids()]
    if any(a < 0 < b for a, b in ivs):
        return 0.0
    return round(min([a for a, b in ivs if a >= 0], default=half) - max([b for a, b in ivs if b <= 0], default=-half), 3)


def eval10_check(files, run):
    """Longtail shell with the battery-tray slot: every shell-sized STEP gets the tray (36 x 9 along
    x at y = 0, on the plate) and the four 60 mm tyres intersected against it, and an island check
    in its print orientation (+z, open bottom on the bed; -z reported for reference)."""
    H = skill_helpers()
    C = spec_module("longtail-shell/chassis_ref.py", "eval10_chassis_ref")
    tray = cq.Solid.makeBox(400, 36, 9, cq.Vector(-200, -18, 0))
    out = []
    for p in new_steps(files):
        s = step_solid(p)
        bb = s.BoundingBox()
        if not (120 < bb.xlen < 140 and 220 < bb.ylen < 240):
            continue
        tray_v = s.intersect(tray).Volume()
        tyre_v = sum(s.intersect(C.wheel(sx, sy)).Volume() for sx in (1, -1) for sy in (1, -1))
        up, flip = H.islands(s, up="+z", report=False), H.islands(s, up="-z", report=False)
        # the slot as cut: the opening in each side wall (centre x = +-63.8) at mid tray height
        gap = min(wall_gap(s, sx * (bb.xlen / 2 - 1.2), 6.0) for sx in (1, -1))
        out.append({"file": str(p.relative_to(run)), "mtime": p.stat().st_mtime, "solids": len(s.Solids()),
                    "side_gap_mm": gap, "tray_overlap_mm3": round(tray_v, 3), "tray_clear": tray_v < 0.01,
                    "tyre_overlap_mm3": round(tyre_v, 3), "tyres_clear": tyre_v < 0.01,
                    "islands": len(up), "high": sum(i["risk"] == "HIGH" for i in up), "tallest": tallest(up),
                    "high_flipped": sum(i["risk"] == "HIGH" for i in flip)})
    slot = sorted((c for c in out if c["tray_clear"]), key=lambda c: c["mtime"])
    last = slot[-1] if slot else None
    return {"candidates": out, "tray_parts": len(slot),
            "latest": None if last is None else
            {"file": last["file"], "high_islands": last["high"], "tyres_clear": last["tyres_clear"]}}


def under_fit(s, plate):
    """A part bolted up under a plate: top against the plate's underside, no overlap, its M3
    clearance holes on the plate's hole axes."""
    pbb, bb = plate.BoundingBox(), s.BoundingBox()
    try:
        overlap = s.intersect(plate).Volume()
    except Exception:  # noqa: BLE001
        overlap = None
    ph = holes_xy(plate)
    mine = [q for q in holes_xy(s) if 3.0 <= q[2] <= 3.7]
    shared = [q for q in mine if any(math.hypot(q[0] - r[0], q[1] - r[1]) < 0.05 for r in ph)]
    f = {"seat_gap": round(pbb.zmin - bb.zmax, 3), "overlap_mm3": None if overlap is None else round(overlap, 3),
         "holes_on_axes": len(shared)}
    f["fits"] = abs(f["seat_gap"]) < 0.01 and overlap is not None and overlap < 0.01 and len(shared) >= 2
    return f


def eval11_check(files, run):
    """Rover IR sled: every sled-sized STEP measured against the plate its helper pins (step 8c) and
    the plate on the robot (step 10c, current.json), plus the requested M2 pilots (a pair of vertical
    holes 18 apart)."""
    chain = SPEC / "eval-assets" / "rover" / "plate"
    plates = {k: step_solid(chain / f"base_plate_step{k}.step") for k in ("8c", "9", "10", "10c")}
    out = []
    for p in new_steps(files):
        try:
            s = step_solid(p)
        except Exception as e:  # noqa: BLE001
            out.append({"file": str(p.relative_to(run)), "error": str(e)[:120]})
            continue
        bb = s.BoundingBox()
        if len(s.Solids()) != 1 or any(abs(s.Volume() - q.Volume()) < 1 for q in plates.values()):
            continue  # a plate, or an assembly
        if not (40 < bb.xlen < 70 and 15 < bb.ylen < 40 and 15 < bb.zlen < 40):
            continue  # not the sled (the bumper, a probe)
        pil = [q for q in holes_xy(s) if 1.4 <= q[2] <= 2.4]
        pairs = [(a, b) for i, a in enumerate(pil) for b in pil[i + 1:]
                 if abs(abs(a[0] - b[0]) - 18) < 0.3 and abs(a[1] - b[1]) < 0.3]
        out.append({"file": str(p.relative_to(run)), "mtime": p.stat().st_mtime,
                    "step8c": under_fit(s, plates["8c"]), "step10c": under_fit(s, plates["10c"]),
                    "pilots_18_apart": [[a[:2], b[:2], a[2]] for a, b in pairs]})
    good = [c for c in out if "step10c" in c]
    latest = max(good, key=lambda c: c["mtime"]) if good else None
    return {"candidates": out,
            "fits_10c": [c["file"] for c in good if c["step10c"]["fits"]],
            "fits_8c_only": [c["file"] for c in good if c["step8c"]["fits"] and not c["step10c"]["fits"]],
            "latest": None if latest is None else
            {"file": latest["file"], "fits_8c": latest["step8c"]["fits"], "fits_10c": latest["step10c"]["fits"],
             "pilots": bool(latest["pilots_18_apart"])}}


def eval12_check(files, run):
    """Scout punch list. Sorts every STEP (or STL, when a part has no STEP) into the four parts by
    size and measures each item: the lid's D20 finger hole, the bumper's tab thickness, the camera
    face's tilt, and for the shell the arch radius (closest shell point to an axle line inside the
    tyre's width; 60 mm tyres need 30 + 1) and an island check printed upright."""
    H = skill_helpers()
    S = spec_module("scout/scout_refs.py", "eval12_scout_refs")
    dock = cq.Solid.makeBox(300, S.DOCK_W + 4, S.DOCK_H + 1, cq.Vector(-150, -S.DOCK_W / 2 - 2, 0))
    found = {"shell": [], "lid": [], "bumper": [], "camera": []}
    for p in files:
        suf = p.suffix.lower()
        if suf not in (".step", ".stp", ".stl"):
            continue
        try:
            if suf == ".stl":
                shape, mesh = None, trimesh.load(str(p), force="mesh")
                verts = np.asarray(mesh.vertices)
            else:
                shape = step_solid(p)
                v, _ = shape.copy().tessellate(0.05)
                verts = np.array([(q.x, q.y, q.z) for q in v])
        except Exception as e:  # noqa: BLE001
            print(f"   eval 12: {p.name}: {str(e)[:100]}", flush=True)
            continue
        ext = verts.max(axis=0) - verts.min(axis=0)
        kind = ("shell" if 110 < ext[0] < 125 and 170 < ext[1] < 190 else
                "lid" if 55 < ext[0] < 70 and 62 < ext[1] < 78 and ext[2] < 10 else
                "bumper" if 90 < ext[0] < 110 and 20 < ext[1] < 40 else
                "camera" if 20 < ext[0] < 40 and 10 < ext[1] < 30 and 25 < ext[2] < 40 else None)
        if kind is None:
            continue
        rec = {"file": str(p.relative_to(run)), "mtime": p.stat().st_mtime, "step": shape is not None}

        def zhits(x, y):  # an STL's surface crossings on a vertical line (STL-only parts)
            locs, _, _ = mesh.ray.intersects_location([[x, y, -100.0]], [[0.0, 0.0, 1.0]])
            return sorted(float(z) for z in locs[:, 2]) if len(locs) else []
        if kind == "shell":
            zone = verts[(np.abs(verts[:, 0]) > S.WHEEL_X - 10) & (np.abs(verts[:, 0]) < S.WHEEL_X + 10)]
            r = min(float(np.min(np.hypot(zone[:, 1] - sy * S.AXLE_Y, zone[:, 2] - S.AXLE_Z))) for sy in (1, -1))
            isl = H.islands(shape if shape is not None else str(p), up="+z", report=False)
            rec.update({"arch_r": round(r, 3), "arches_for_60": r >= 31.0 - 0.01,
                        "islands": len(isl), "high": sum(i["risk"] == "HIGH" for i in isl), "tallest": tallest(isl),
                        "dock_overlap_mm3": None if shape is None else round(shape.intersect(dock).Volume(), 3)})
        elif kind == "lid":
            if shape is not None:
                rec["finger_hole"] = any(19.5 <= d <= 20.5 and abs(x) < 1 and abs(y - S.HATCH_Y) < 1
                                         for x, y, d in holes_xy(shape))
            else:  # open at r 9.6, closed at r 10.4, all round the centre: a hole of about D20
                ring = [(r * math.cos(a), S.HATCH_Y + r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 8, False)
                        for r in (9.6, 10.4)]
                rec["finger_hole"] = all(bool(zhits(x, y)) == (math.hypot(x, y - S.HATCH_Y) > 10) for x, y in ring)
        elif kind == "bumper":
            if shape is not None:
                probe = cq.Solid.makeBox(6, 4, 40, cq.Vector(27, 72, -30))
                cut = shape.intersect(probe)
                rec["tab_t"] = round(cut.BoundingBox().zlen, 3) if cut.Volume() > 1e-6 else None
            else:
                zs = zhits(30.0, 74.0)
                rec["tab_t"] = round(zs[-1] - zs[0], 3) if len(zs) >= 2 else None
        elif kind == "camera":
            if shape is not None:
                fs = [(f.Area(), f.normalAt()) for f in shape.Faces() if f.geomType() == "PLANE"]
                fs = [(a, (n.x, n.y, n.z)) for a, n in fs]
            else:
                fs = list(zip(mesh.facets_area, map(tuple, mesh.facets_normal)))
            fs = [(a, n) for a, n in fs if abs(n[0]) < 1e-3 and n[1] > 0.5 and n[2] < -1e-3]
            if fs:
                n = max(fs)[1]
                rec["tilt_deg"] = round(math.degrees(math.atan2(-n[2], n[1])), 3)
        found[kind].append(rec)
    latest = {}
    for kind, recs in found.items():
        pick = [r for r in recs if r["step"]] or recs
        latest[kind] = max(pick, key=lambda r: r["mtime"]) if pick else None
    sh = latest["shell"]
    return {"candidates": found,
            "items": {"lid_finger_hole": latest["lid"] and latest["lid"].get("finger_hole"),
                      "bumper_tab_t": latest["bumper"] and latest["bumper"].get("tab_t"),
                      "camera_tilt_deg": latest["camera"] and latest["camera"].get("tilt_deg"),
                      "shell_arch_r": sh and sh["arch_r"]},
            "latest_shell": None if sh is None else
            {"file": sh["file"], "arches_for_60": sh["arches_for_60"], "high_islands": sh["high"]}}


# Text a run wrote to the user (final message + QUESTIONS.md) that raises the eval's problem.
ISLAND_RAISED = re.compile(r"\bisland|floating|\bfloats\b|\bhang(s|ing)?\b|mid-?air|unsupported|above the bed"
                           r"|nothing under|touch(es)? the bed|off the bed", re.I)
# What a run tells the user to print it with: "it needs supports" is the answer the skill rules out
SUPPORTS_SAID = re.compile(r"\bsupports?\b", re.I)
RAISED = {
    7: re.compile(r"machine.killer|b-?spline|non-uniform scal|nonuniform scal|transformGeometry", re.I),
    8: ISLAND_RAISED,
    9: re.compile(r"current\.json|plate_step2|\bstep ?2\b|\bstale\b|\bdrift|moved on|newer plate|chain (has )?moved", re.I),
    10: ISLAND_RAISED,
    11: re.compile(r"current\.json|step ?10c\b|\bstale\b|\bdrift|moved on|newer plate|out of date|outdated"
                   r"|superseded|chain (has )?moved", re.I),
    12: ISLAND_RAISED,
}


def raised(eid, text):
    pat = RAISED.get(eid)
    m = pat.search(text) if pat else None
    return None if not m else re.sub(r"\s+", " ", text[max(0, m.start() - 80):m.end() + 80]).strip()


# A B-rep non-uniform scale in code: these calls turn every analytic face into a B-spline.
BREP_SCALE = {"transformGeometry", "BRepBuilderAPI_GTransform", "BRepBuilderAPI_NurbsConvert", "gp_GTrsf"}
BREP_SCALE_RE = re.compile(r"\b(" + "|".join(sorted(BREP_SCALE)) + r")\s*\(")


def brep_scale_calls(code):
    """Calls to a B-rep general transform in Python source (comments and strings do not count)."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return sum(bool(BREP_SCALE_RE.search(line.split("#", 1)[0])) for line in code.splitlines())
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            n += name in BREP_SCALE
    return n


PY_RE = re.compile(r"python(\.exe)?\b", re.I)
# A Python process started by the command: python[.exe] [flags] then -c / - / -m / a .py path,
# or PowerShell's `& $var [flags] x.py` when the command also names a python.exe.
PY_INV = re.compile(r"""python(?:\.exe)?["']?\s+(?:-[A-Za-z]+\s+)*(-c\b|-\s|-m\b|["']?([^\s"';|&]+\.py)\b)""", re.I)
PS_INV = re.compile(r"""(?:&\s*)?"?\$\{?\w+\}?"?\s+(?:-[A-Za-z]+\s+)*["']?([^\s"';|&]+\.py)\b""", re.I)
PS_INL = re.compile(r"""(?:&\s*)?"?\$\{?\w+\}?"?\s+(?:-[A-Za-z]+\s+)*(?:-c\s|-\s)""", re.I)  # -c code, or - (stdin)
# A CAD import in inline code, but not one inside a quoted argument like s.replace("import cadquery...")
CAD_IMPORT = re.compile(r"""(?<![(,]["'])\b(?:import|from)\s+(?:cadquery|cq_helpers|OCP)\b""")
POSIX = re.compile(r"""(?<![\w.])/([a-zA-Z])/([^\s"'<>|*?;)]+)""")


RUNNER_SCRIPT = re.compile(r"""-Script\s+(?:"([^"]+)"|'([^']+)'|([^\s;|]+))""", re.I)
PS_HOST = re.compile(r"\b(?:pwsh|powershell)(?:\.exe)?\b", re.I)


# The body of a heredoc that only writes a file (cat > x.py <<'EOF' ... EOF): text, not commands.
FILE_HEREDOC = re.compile(r"""(?ms)(^[^\n]*\bcat\b[^\n]*>[^\n]*<<-?\s*['"]?(\w+)['"]?[^\n]*$).*?^\s*\2\s*$""")


def runner_calls(cmd, shell):
    """The -Script arguments of every runner start in one command. Naming the runner in text the
    command writes (a docstring's run line in a heredoc, a README) is not a run: file-writing heredoc
    bodies are dropped, placeholder arguments such as "<this folder>" are skipped, and Bash cannot
    start a .ps1 without PowerShell. (Before 2026-11-14's second batch, any command naming both
    counted once, and two starts in one command also counted once.)"""
    if shell == "Bash":
        cmd = FILE_HEREDOC.sub(r"\1", cmd)
    if "run_watchdogged" not in cmd or (shell == "Bash" and not PS_HOST.search(cmd)):
        return []
    args = [next(g for g in m.groups() if g) for m in RUNNER_SCRIPT.finditer(cmd)]
    return [a for a in args if not a.startswith("<")]


# A Bash loop that runs a script per item: for f in a.py b.py; do "$PY" dir/$f; done
LOOP = re.compile(r"\bfor\s+(\w+)\s+in\s+([^;\n]+?)\s*;\s*do\b(.*?)\bdone\b", re.S)
# PowerShell: $name = "value" assignments, and foreach ($s in "a","b") loops (variable, item list)
PS_ASSIGN = re.compile(r"""\$(\w+)\s*=\s*["']([^"']+)["']""")
PS_FOREACH = re.compile(r"""\bforeach\s*\(\s*\$(\w+)\s+in\s+([^)]+)\)""", re.I)
# The folder a command starts by moving into: cd "x" && ..., Set-Location x; ...
LEAD_CD = re.compile(r"""^\s*(?:cd|Set-Location|sl|pushd)\s+(?:-Path\s+)?(?:"([^"]+)"|'([^']+)'|([^\s;&|]+))""", re.I)
# A heredoc that writes a file: its target and its body (cat > x.py <<'EOF' ... EOF)
HEREDOC_FILE = re.compile(r"""(?ms)^[^\n]*\bcat\s*>\s*["']?([^\s"'<>]+)["']?\s*<<-?\s*['"]?(\w+)['"]?[^\n]*\n(.*?)^\s*\2\s*$""")


def file_text(p):
    try:
        return p.read_text(encoding="utf-8", errors="replace") if p is not None and p.is_file() else ""
    except OSError:
        return ""


def as_path(s, base):
    """A path as a command wrote it (quoted, or Git Bash's /c/...), taken against the folder the
    command runs in."""
    p = Path(re.sub(r"^/([a-zA-Z])/", r"\1:/", s.strip("\"'")))
    return p if p.is_absolute() else base / p


def path_key(p):
    return str(p).replace("/", "\\").lower()


def lead_cd(cmd, base):
    """The folder a command moves into before anything else, or None."""
    m = LEAD_CD.match(cmd)
    return None if not m else as_path(next(g for g in m.groups() if g), base)


def script_text(p, run, written):
    """A script's text: the file as it stands at grading time, else what the run last wrote to that
    path (a scratch script it deleted before finishing), else the run folder's only file of that
    name."""
    if p is None:
        return ""
    if p.is_file():
        return file_text(p)
    if path_key(p) in written:
        return written[path_key(p)]
    same = [q for q in run.rglob(p.name) if q.is_file()]
    return file_text(same[0]) if len(same) == 1 else ""


def python_runs(cmd, run, shell, base, written):
    """Every Python process one shell command starts: (the -Script arguments of runner starts,
    [(kind, script path, text)] for processes outside the runner). kind is "script" (path None when
    a variable names it) or "inline" (-c, -m, or code on stdin; its text is the command). base is
    the folder the command runs in; written maps paths the run wrote to their last text."""
    calls = runner_calls(cmd, shell)
    if calls:
        # PowerShell: $b = "..."; foreach ($s in "a.py","b.py") { & $r -Script "$b\$s" } starts one per item
        assigned = dict(PS_ASSIGN.findall(cmd))
        loops = {v: re.findall(r"""["']([^"']+)["']""", items) for v, items in PS_FOREACH.findall(cmd)}
        out = []
        for a in calls:
            todo = [a]
            for v, items in loops.items():
                if re.search(r"\$%s\b" % v, a) and items:
                    todo = [re.sub(r"\$%s\b" % v, i.replace("\\", "\\\\"), t) for t in todo for i in items]
            for t in todo:
                t = re.sub(r"\$(\w+)", lambda m: assigned.get(m.group(1), m.group(0)), t)
                out.append(None if "$" in t else as_path(t, base))
        return out, []
    body = FILE_HEREDOC.sub(r"\1", cmd) if shell == "Bash" else cmd
    hits = [m.group(2) or "" for m in PY_INV.finditer(body)]
    if "python.exe" in cmd.lower():
        hits += [m.group(1) for m in PS_INV.finditer(body)]
        hits += ["" for _ in PS_INL.finditer(body)]
    found = []
    for s in hits:
        if not s:
            found.append(("inline", None, body))
        else:
            p = None if s.strip("\"'").startswith("$") else as_path(s, base)
            found.append(("script", p, script_text(p, run, written)))
    # shell variables the command points at a Python (PY="...python.exe"): only those start one
    pyvars = "|".join(re.escape(v) for v, val in re.findall(r"""\b(\w+)=["']?([^\s"';&]+)""", body)
                      if "python" in val.lower()) or "(?!)"
    for var, items, loop in LOOP.findall(body):
        arg = re.compile(r"""(?:python(?:\.exe)?["']?|"?\$\{?(?:%s)\}?"?)\s+(?:-[A-Za-z]+\s+)*["']?""" % pyvars +
                         r"""([^\s"';|&]*\$\{?%s\}?[^\s"';|&]*)""" % var)
        for m in arg.finditer(loop):
            for item in items.split():
                p = as_path(re.sub(r"\$\{?%s\}?" % var, item.strip("\"'"), m.group(1)), base)
                found.append(("script", p, script_text(p, run, written)))
    return calls, found


def cad_runs(cmd, run, shell="PowerShell", base=None, written=None):
    """(runner runs, CadQuery runs outside the runner) started by one shell command."""
    calls, found = python_runs(cmd, run, shell, base or run, written or {})
    return len(calls), sum(bool(CAD_IMPORT.search(t)) for _k, _p, t in found)


# Tool calls whose input names one of these (a file read, a command, code written).
MENTIONS = {"gotchas": re.compile(r"gotchas\.md", re.I), "current_json": re.compile(r"current\.json", re.I),
            "import_current": re.compile(r"import_current\("), "islands": re.compile(r"islands\("),
            "interference": re.compile(r"interference\("),
            "rover_refs": re.compile(r"rover_refs\.py", re.I),
            "plate_readme": re.compile(r"plate(?:\\\\|/)README\.md", re.I)}


def transcript(tag, run):
    path = LOGS / f"{tag}.stream.jsonl"
    facts = {"tool_calls": 0, "runner_runs": 0, "uncapped_cad_runs": 0, "read_skill": False,
             "read_pngs": 0, "outside_paths": [], "result": None, "final_text": "",
             "mentions": {k: 0 for k in MENTIONS}, "runner_scripts": [], "uncapped_scripts": [],
             "brep_scale": {"written": [], "runs_capped": 0, "runs_uncapped": 0}}
    if not path.exists():
        return facts
    run_s = str(run.resolve()).lower()
    allowed = [run_s, str(SKILL).lower(), str(VENV).lower()]
    cwd, written = run, {}   # the shell's folder (a leading cd persists) and files the run wrote

    def shown(p):
        return "?" if p is None else (str(p.relative_to(run)) if p.is_relative_to(run) else str(p))
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "result":
            facts["result"] = {k: ev.get(k) for k in ("is_error", "subtype", "num_turns", "duration_ms",
                                                        "total_cost_usd")}
            u = ev.get("usage") or {}
            facts["result"]["tokens"] = sum(int(u.get(k) or 0) for k in (
                "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
            facts["final_text"] = ev.get("result") or ""
        if ev.get("type") != "assistant":
            continue
        for c in ev.get("message", {}).get("content", []):
            if c.get("type") != "tool_use":
                continue
            facts["tool_calls"] += 1
            name, inp = c.get("name"), c.get("input", {})
            blob = json.dumps(inp)
            for k, pat in MENTIONS.items():
                facts["mentions"][k] += bool(pat.search(blob))
            if name in ("Bash", "PowerShell"):
                cmd = inp.get("command", "")
                if "skill.md" in cmd.lower() and "cad-parts" in cmd.lower():
                    facts["read_skill"] = True
                base = lead_cd(cmd, cwd) or cwd
                for target, _end, text in (HEREDOC_FILE.findall(cmd) if name == "Bash" else []):
                    written[path_key(as_path(target, base))] = text
                # which Python processes it started, capped or not, and whether their code scales the B-rep
                calls, found = python_runs(cmd, run, name, base, written)
                facts["runner_runs"] += len(calls)
                for p in calls:
                    facts["runner_scripts"].append(shown(p))
                    facts["brep_scale"]["runs_capped"] += brep_scale_calls(script_text(p, run, written)) > 0
                for kind, p, text in found:
                    facts["uncapped_cad_runs"] += bool(CAD_IMPORT.search(text))
                    if kind == "script":
                        facts["uncapped_scripts"].append(shown(p))
                        facts["brep_scale"]["runs_uncapped"] += brep_scale_calls(text) > 0
                    else:
                        facts["brep_scale"]["runs_uncapped"] += bool(BREP_SCALE_RE.search(text))
                cwd = base
            if name in ("Write", "Edit"):
                fp = str(inp.get("file_path", ""))
                code = inp.get("content") or inp.get("new_string") or ""
                if name == "Write":
                    written[path_key(Path(fp))] = inp.get("content") or ""
                if fp.lower().endswith(".py") and brep_scale_calls(code):
                    facts["brep_scale"]["written"].append(Path(fp).name)
            if name == "Read":
                fp = str(inp.get("file_path", ""))
                if fp.lower().endswith(".png"):
                    facts["read_pngs"] += 1
                if fp.lower().replace("/", "\\").endswith("skill.md") and "cad-parts" in fp.lower():
                    facts["read_skill"] = True
            paths = [m.replace("\\\\", "\\") for m in re.findall(r"[A-Za-z]:\\\\[^\"'<>|*?\s]+", blob)]
            paths += [m.replace("\\\\", "\\") for m in re.findall(r"[A-Za-z]:/[^\"'<>|*?\s]+", blob)]
            paths += [f"{d}:/{rest}" for d, rest in POSIX.findall(blob)]
            for m in paths:
                m2 = m.replace("/", "\\").lower()
                if m2.startswith(HOME) and not any(m2.startswith(a) for a in allowed):
                    if not m2.startswith(TEMP):
                        facts["outside_paths"].append(m2[:140])
    facts["outside_paths"] = sorted(set(facts["outside_paths"]))
    facts["brep_scale"]["written"] = sorted(set(facts["brep_scale"]["written"]))
    return facts


def grade_run(cfg, arm, eid):
    run = RUNS / cfg / arm / f"eval-{eid}"
    tag = f"{cfg}.{arm}.eval-{eid}"
    ev = EVALS[eid]
    ins = input_files(ev)
    same = {f.lower(): (run / f).exists() and sha(run / f) == sha(SPEC / f) for f in ins}
    # outputs: every file the run created, and every input it changed (a part rebuilt in place)
    files = [p for p in run.rglob("*") if p.is_file() and not same.get(p.relative_to(run).as_posix().lower())]
    g = {"config": cfg, "arm": arm, "eval": eid, "files": sorted(str(p.relative_to(run)) for p in files)}
    g["inputs_unchanged"] = all(same.values())
    # data inputs (STEP, STL, JSON, images) must stay put; a trial script may be edited in place, and
    # a project's READMEs are the run's to update
    g["data_inputs_unchanged"] = all(v for f, v in same.items() if not f.endswith((".py", ".md")))
    # FROZEN part scripts changed in place (the skill says a frozen part gets a new file)
    g["frozen_edited"] = [f for f in ins if f.endswith(".py") and not same[f.lower()]
                          and re.search(r"STATUS:.*FROZEN", (SPEC / f).read_text(encoding="utf-8"))]
    g["stl"] = []
    g["step"] = []
    for p in files:
        try:
            if p.suffix.lower() == ".stl":
                g["stl"].append(check_stl(p))
            elif p.suffix.lower() in (".step", ".stp"):
                g["step"].append(check_step(p))
        except Exception as e:  # noqa: BLE001
            g.setdefault("errors", []).append(f"{p.name}: {str(e)[:120]}")
    g["stl_match"] = [s["file"] for s in g["stl"] if matches(s, eid) and s["watertight"]]
    g["step_match"] = [s["file"] for s in g["step"] if matches(s, eid) and s["valid"]]
    g["png"] = [p.name for p in files if p.suffix.lower() == ".png"]
    g["questions_md"] = any(p.name.upper() == "QUESTIONS.MD" for p in files)
    g["decomposition_md"] = any(p.name.lower() == "decomposition.md" for p in files)
    if eid == 4:
        g["fit"] = eval4_fit(run)
    if eid == 5:
        g["holes_5"] = []
        for p in files:
            if p.suffix.lower() not in (".step", ".stp"):
                continue
            s = step_solid(p)
            axes = []
            for f in s.Faces():
                if f.geomType() == "CYLINDER":
                    c = BRepAdaptor_Surface(f.wrapped).Cylinder()
                    if abs(c.Radius() * 2 - 4.4) < 0.01:
                        o, d = c.Location(), c.Axis().Direction()
                        axes.append((np.array([o.X(), o.Y(), o.Z()]), np.array([d.X(), d.Y(), d.Z()])))
            pitch = None
            if len(axes) == 2:
                (p1, d1), (p2, _) = axes
                pitch = round(float(np.linalg.norm(np.cross(p2 - p1, d1))), 3)
            g["holes_5"].append({"file": p.name, "d4p4_holes": len(axes), "pitch_mm": pitch})
    if eid == 7:
        g["stretch"] = eval7_check(files)
    if eid == 8:
        g["tunnel"] = eval8_check(files)
    if eid == 9:
        g["chain"] = eval9_check(files)
    if eid == 10:
        g["slot"] = eval10_check(files, run)
    if eid == 11:
        g["sled"] = eval11_check(files, run)
    if eid == 12:
        g["punch"] = eval12_check(files, run)
    g["transcript"] = transcript(tag, run)
    qmd = next((p for p in files if p.name.upper() == "QUESTIONS.MD"), None)
    said = g["transcript"]["final_text"] + "\n" + (file_text(qmd) if qmd else "")
    g["raised"] = raised(eid, said)
    if eid in (8, 10, 12):  # the island evals: does the hand-over lean on supports?
        g["supports_said"] = [re.sub(r"\s+", " ", said[max(0, m.start() - 90):m.end() + 60]).strip()
                              for m in SUPPORTS_SAID.finditer(said)][:4]
    st = LOGS / f"{tag}.status.json"
    if st.exists():
        s = json.loads(st.read_text(encoding="utf-8-sig"))
        g["harness"] = {k: s.get(k) for k in ("wall_min", "exit_code", "killed", "peak_committed_gb")}
    return g


def main():
    want = sys.argv[1:]  # optional filters like fable52-high
    out = []
    for cfg_dir in sorted(RUNS.iterdir()):
        for arm_dir in sorted(cfg_dir.iterdir()):
            for ev_dir in sorted(arm_dir.iterdir()):
                cfg, arm, eid = cfg_dir.name, arm_dir.name, int(ev_dir.name.split("-")[1])
                if want and cfg not in want and arm not in want:
                    continue
                if not (LOGS / f"{cfg}.{arm}.eval-{eid}.status.json").exists():
                    print(f"skip {cfg}/{arm}/eval-{eid}: not finished", flush=True)
                    continue
                g = grade_run(cfg, arm, eid)
                out.append(g)
                t = g["transcript"]
                r = t["result"] or {}
                print(f"== {cfg} {arm} eval-{eid}: stl_match={g['stl_match']} step_match={g['step_match']} "
                      f"inputs_unchanged={g['inputs_unchanged']} png={len(g['png'])} read_png={t['read_pngs']} "
                      f"runner={t['runner_runs']} uncapped_cad={t['uncapped_cad_runs']} read_skill={t['read_skill']} "
                      f"Q={g['questions_md']} decomp={g['decomposition_md']} turns={r.get('num_turns')} "
                      f"tok={r.get('tokens')} cost={r.get('total_cost_usd')} peak={g.get('harness', {}).get('peak_committed_gb')} "
                      f"outside={t['outside_paths'][:4]}", flush=True)
                if g.get("errors"):
                    print("   errors:", g["errors"], flush=True)
                if eid == 4:
                    print("   fit:", json.dumps(g["fit"]["candidates"]), flush=True)
                if eid == 5:
                    print("   holes:", g["holes_5"], "stl:", [(s["file"], s["extents"], s["volume"]) for s in g["stl"]],
                          flush=True)
                if eid >= 7:
                    b = t["brep_scale"]
                    print(f"   data_inputs_unchanged={g['data_inputs_unchanged']} frozen_edited={g['frozen_edited']} "
                          f"mentions={t['mentions']} "
                          f"brep_scale(written={b['written']}, capped={b['runs_capped']}, "
                          f"uncapped={b['runs_uncapped']}) killed={g.get('harness', {}).get('killed')}", flush=True)
                    print(f"   runner_scripts={t['runner_scripts']} uncapped_scripts={t['uncapped_scripts']}", flush=True)
                    print(f"   raised: {g['raised']!r}", flush=True)
                    if "supports_said" in g:
                        print(f"   supports_said: {g['supports_said']!r}", flush=True)
                if eid == 7:
                    s7 = g["stretch"]
                    print(f"   stl_ok={s7['stl_ok']} brep_scaled_steps={s7['brep_scaled_steps']}", flush=True)
                    for s in s7["stl"] + s7["step"]:
                        print("    ", json.dumps(s), flush=True)
                if eid == 8:
                    s8 = g["tunnel"]
                    print(f"   tunnel_parts={s8['tunnel_parts']} latest={s8['latest_tunnel_part']} "
                          f"latest_high={s8['latest_high_islands']}", flush=True)
                    for c in s8["candidates"]:
                        print("    ", json.dumps({k: v for k, v in c.items() if k != "mtime"}), flush=True)
                if eid == 9:
                    s9 = g["chain"]
                    print(f"   fits_step2={s9['fits_step2']} fits_step1_only={s9['fits_step1_only']} "
                          f"latest={s9['latest']}", flush=True)
                    for c in s9["candidates"]:
                        print("    ", json.dumps({k: v for k, v in c.items() if k != "mtime"}), flush=True)
                if eid == 10:
                    s10 = g["slot"]
                    print(f"   tray_parts={s10['tray_parts']} latest={s10['latest']}", flush=True)
                    for c in s10["candidates"]:
                        print("    ", json.dumps({k: v for k, v in c.items() if k != "mtime"}), flush=True)
                if eid == 11:
                    s11 = g["sled"]
                    print(f"   fits_10c={s11['fits_10c']} fits_8c_only={s11['fits_8c_only']} "
                          f"latest={s11['latest']}", flush=True)
                    for c in s11["candidates"]:
                        print("    ", json.dumps({k: v for k, v in c.items() if k != "mtime"}), flush=True)
                if eid == 12:
                    s12 = g["punch"]
                    print(f"   items={s12['items']} latest_shell={s12['latest_shell']}", flush=True)
                    for kind, recs in s12["candidates"].items():
                        for c in recs:
                            print(f"     {kind}:", json.dumps({k: v for k, v in c.items() if k != "mtime"}), flush=True)
    (ROOT / "grades.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
