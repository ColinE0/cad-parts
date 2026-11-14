"""Grades every finished cad-parts eval run: geometry of the parts each run produced, plus process
facts read from its transcript. Writes grades.json and prints one block per run.

Run it through the cad-parts runner with the eval venv (it imports STEP files). Eval 8's island
check imports cq_helpers from the skill-under-test copy.
"""
import ast
import hashlib
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


# Text a run wrote to the user (final message + QUESTIONS.md) that raises the eval's problem.
RAISED = {
    7: re.compile(r"machine.killer|b-?spline|non-uniform scal|nonuniform scal|transformGeometry", re.I),
    8: re.compile(r"\bisland|floating|\bfloats\b|\bhang(s|ing)?\b|mid-?air|unsupported|above the bed|nothing under", re.I),
    9: re.compile(r"current\.json|plate_step2|\bstep ?2\b|\bstale\b|\bdrift|moved on|newer plate|chain (has )?moved", re.I),
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


def cad_runs(cmd, run, shell="PowerShell"):
    """(runner runs, CadQuery runs outside the runner) started by one shell command."""
    calls = runner_calls(cmd, shell)
    if calls:
        return len(calls), 0
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


def ran_scripts(cmd, run, shell="PowerShell"):
    """(scripts run under the runner, Python scripts run outside it, inline -c code run outside it)
    for one shell command. A script named by a variable shows as '?'."""
    def resolve(s):
        if s.startswith("$"):
            return None
        p = Path(s.strip("\"'"))
        return p if p.is_absolute() else run / p
    calls = runner_calls(cmd, shell)
    if calls:
        return [resolve(a) for a in calls], [], []
    scripts, inline = [], []
    hits = [(m.group(1), m.group(2)) for m in PY_INV.finditer(cmd)]
    if "python.exe" in cmd.lower():
        hits += [(m.group(1), m.group(1)) for m in PS_INV.finditer(cmd)]
        hits += [("-c", None) for _ in PS_INL.finditer(cmd)]
    for _flag, script in hits:
        if script:
            scripts.append(resolve(script))
        else:
            inline.append(cmd)
    return [], scripts, inline


def file_text(p):
    try:
        return p.read_text(encoding="utf-8", errors="replace") if p is not None and p.is_file() else ""
    except OSError:
        return ""


# Tool calls whose input names one of these (a file read, a command, code written).
MENTIONS = {"gotchas": re.compile(r"gotchas\.md", re.I), "current_json": re.compile(r"current\.json", re.I),
            "import_current": re.compile(r"import_current\("), "islands": re.compile(r"islands\("),
            "interference": re.compile(r"interference\(")}


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
                capped, uncapped = cad_runs(cmd, run, name)
                facts["runner_runs"] += capped
                facts["uncapped_cad_runs"] += uncapped
                # which scripts ran, and whether their code (as it stands at the end) scales the B-rep
                rc, ru, inline = ran_scripts(cmd, run, name)
                for key, scripts in (("capped", rc), ("uncapped", ru)):
                    for p in scripts:
                        facts["runner_scripts" if key == "capped" else "uncapped_scripts"].append(
                            "?" if p is None else (str(p.relative_to(run)) if p.is_relative_to(run) else str(p)))
                        facts["brep_scale"][f"runs_{key}"] += brep_scale_calls(file_text(p)) > 0
                facts["brep_scale"]["runs_uncapped"] += sum(bool(BREP_SCALE_RE.search(x)) for x in inline)
            if name in ("Write", "Edit"):
                fp = str(inp.get("file_path", ""))
                code = inp.get("content") or inp.get("new_string") or ""
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
    inputs = {str((run / f).resolve()).lower() for f in ev["files"]}
    files = [p for p in run.rglob("*") if p.is_file() and str(p.resolve()).lower() not in inputs]
    g = {"config": cfg, "arm": arm, "eval": eid, "files": sorted(str(p.relative_to(run)) for p in files)}
    g["inputs_unchanged"] = all((run / f).exists() and sha(run / f) == sha(SPEC / f) for f in ev["files"])
    # data inputs (STEP, STL, JSON, images) must stay put; a trial script may be edited in place
    g["data_inputs_unchanged"] = all((run / f).exists() and sha(run / f) == sha(SPEC / f)
                                     for f in ev["files"] if not f.endswith(".py"))
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
    g["transcript"] = transcript(tag, run)
    qmd = next((p for p in files if p.name.upper() == "QUESTIONS.MD"), None)
    said = g["transcript"]["final_text"] + "\n" + (file_text(qmd) if qmd else "")
    g["raised"] = raised(eid, said)
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
                if eid in (7, 8, 9):
                    b = t["brep_scale"]
                    print(f"   data_inputs_unchanged={g['data_inputs_unchanged']} mentions={t['mentions']} "
                          f"brep_scale(written={b['written']}, capped={b['runs_capped']}, "
                          f"uncapped={b['runs_uncapped']}) killed={g.get('harness', {}).get('killed')}", flush=True)
                    print(f"   runner_scripts={t['runner_scripts']} uncapped_scripts={t['uncapped_scripts']}", flush=True)
                    print(f"   raised: {g['raised']!r}", flush=True)
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
    (ROOT / "grades.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
