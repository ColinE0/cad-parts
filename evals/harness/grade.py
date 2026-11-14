"""Grades every finished cad-parts eval run: geometry of the parts each run produced, plus process
facts read from its transcript. Writes grades.json and prints one block per run.

Run it through the cad-parts runner with the eval venv (it imports STEP files).
"""
import hashlib
import json
import math
import re
import sys
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


PY_RE = re.compile(r"python(\.exe)?\b", re.I)
# A Python process started by the command: python[.exe] [flags] then -c / - / -m / a .py path,
# or PowerShell's `& $var [flags] x.py` when the command also names a python.exe.
PY_INV = re.compile(r"""python(?:\.exe)?["']?\s+(?:-[A-Za-z]+\s+)*(-c\b|-\s|-m\b|["']?([^\s"';|&]+\.py)\b)""", re.I)
PS_INV = re.compile(r"""(?:&\s*)?"?\$\{?\w+\}?"?\s+(?:-[A-Za-z]+\s+)*["']?([^\s"';|&]+\.py)\b""", re.I)
PS_INL = re.compile(r"""(?:&\s*)?"?\$\{?\w+\}?"?\s+(?:-[A-Za-z]+\s+)*-c\s""", re.I)
# A CAD import in inline code, but not one inside a quoted argument like s.replace("import cadquery...")
CAD_IMPORT = re.compile(r"""(?<![(,]["'])\b(?:import|from)\s+(?:cadquery|cq_helpers|OCP)\b""")
POSIX = re.compile(r"""(?<![\w.])/([a-zA-Z])/([^\s"'<>|*?;)]+)""")


def cad_runs(cmd, run):
    """(runner runs, CadQuery runs outside the runner) started by one shell command."""
    if "run_watchdogged" in cmd and "-Script" in cmd:
        return 1, 0
    uncapped = 0
    hits = [(m.group(1), m.group(2)) for m in PY_INV.finditer(cmd)]
    if "python.exe" in cmd.lower():
        hits += [(m.group(1), m.group(1)) for m in PS_INV.finditer(cmd)]
        hits += [("-c", None) for _ in PS_INL.finditer(cmd)]
    for flag, script in hits:
        if script:
            p = Path(script.strip("\"'"))
            p = p if p.is_absolute() else run / p
            try:
                text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
            except OSError:
                text = ""
            uncapped += int(bool(CAD_IMPORT.search(text)))
        else:
            uncapped += int(bool(CAD_IMPORT.search(cmd)))
    return 0, uncapped


def transcript(tag, run):
    path = LOGS / f"{tag}.stream.jsonl"
    facts = {"tool_calls": 0, "runner_runs": 0, "uncapped_cad_runs": 0, "read_skill": False,
             "read_pngs": 0, "outside_paths": [], "result": None, "final_text": ""}
    if not path.exists():
        return facts
    run_s = str(run.resolve()).lower()
    allowed = [run_s, str(SKILL).lower(), str(VENV).lower()]
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
            if name in ("Bash", "PowerShell"):
                cmd = inp.get("command", "")
                if "skill.md" in cmd.lower() and "cad-parts" in cmd.lower():
                    facts["read_skill"] = True
                capped, uncapped = cad_runs(cmd, run)
                facts["runner_runs"] += capped
                facts["uncapped_cad_runs"] += uncapped
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
    return facts


def grade_run(cfg, arm, eid):
    run = RUNS / cfg / arm / f"eval-{eid}"
    tag = f"{cfg}.{arm}.eval-{eid}"
    ev = EVALS[eid]
    inputs = {str((run / f).resolve()).lower() for f in ev["files"]}
    files = [p for p in run.rglob("*") if p.is_file() and str(p.resolve()).lower() not in inputs]
    g = {"config": cfg, "arm": arm, "eval": eid, "files": sorted(str(p.relative_to(run)) for p in files)}
    g["inputs_unchanged"] = all((run / f).exists() and sha(run / f) == sha(SPEC / f) for f in ev["files"])
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
    g["transcript"] = transcript(tag, run)
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
    (ROOT / "grades.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
