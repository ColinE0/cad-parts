# Copyright 2026 Colin Ezra Wilder. SPDX-License-Identifier: Apache-2.0
"""Self-test for hooks/require_runner.py: feeds it tool calls the way Claude Code does (JSON on
stdin) and checks each is blocked (exit 2) or allowed (exit 0). Plain asserts, ends with DONE.
Run it through the runner like any venv script:
    & ..\\scripts\\run_watchdogged.ps1 -Script .\\test_require_runner.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "require_runner.py"
PY = r"C:\cadquery-venv\Scripts\python.exe"

BLOCK = [
    ("PowerShell", rf"{PY} part.py"),
    ("PowerShell", rf'& "{PY}" -u part.py'),
    ("PowerShell", rf'$py = "{PY}"; & $py -I probe.py'),
    ("PowerShell", rf'cd C:\parts; & {PY} -c "import cadquery as cq"'),
    ("PowerShell", rf"Start-Process -FilePath {PY} -ArgumentList build.py -Wait"),
    ("PowerShell", rf'cmd /c "{PY} part.py"'),
    ("PowerShell", "& $env:CADPARTS_PYTHON part.py"),
    ("Bash", "C:/cadquery-venv/Scripts/python.exe -I part.py"),
    ("Bash", "/c/cadquery-venv/Scripts/python.exe - <<'EOF'\nimport cadquery\nEOF"),
    ("Bash", "cd /c/parts && PYTHONPATH=lib /c/cadquery-venv/Scripts/python.exe part.py"),
    ("Bash", 'PY="C:/cadquery-venv/Scripts/python.exe"; "$PY" part.py'),
    ("Bash", "uv run --python C:/cadquery-venv/Scripts/python.exe part.py"),
    # a runner call in one segment does not excuse a direct call in another
    ("PowerShell", rf'& C:\skill\scripts\run_watchdogged.ps1 -Script a.py; & {PY} b.py'),
]
ALLOW = [
    ("PowerShell", r'& "$env:USERPROFILE\.claude\skills\cad-parts\scripts\run_watchdogged.ps1" -Script C:\parts\part.py -Tail 40'),
    ("PowerShell", rf'& C:\skill\scripts\run_watchdogged.ps1 -Script part.py -Python "{PY}"'),
    ("PowerShell", rf"{PY} -m pip install shapely"),
    ("PowerShell", rf"& {PY} --version"),
    ("PowerShell", rf"Test-Path {PY}"),
    ("PowerShell", r"Copy-Item cq_helpers.py C:\cadquery-venv\Lib\site-packages\ -Force"),
    ("PowerShell", r"Get-ChildItem C:\cadquery-venv\Lib\site-packages -Filter *.py"),
    ("Bash", "python part.py"),
    ("Bash", "ls /c/cadquery-venv/Scripts"),
    ("Bash", 'git commit -m "docs: the venv lives at C:/cadquery-venv/Scripts/python.exe"'),
    ("Bash", "uv pip install --python C:/cadquery-venv/Scripts/python.exe -r requirements.txt"),
    ("Read", rf"{PY} part.py"),     # not a shell tool: never inspected
]


def run(tool, command, env=None):
    payload = {"tool_name": tool, "tool_input": {"command": command}}
    if tool == "Read":
        payload["tool_input"] = {"file_path": command}
    r = subprocess.run([sys.executable, "-I", str(HOOK)], input=json.dumps(payload), capture_output=True,
                       text=True, timeout=30, env=env)
    return r.returncode, r.stderr


env = {k: v for k, v in os.environ.items() if k != "CADPARTS_PYTHON"}
for tool, cmd in BLOCK:
    code, err = run(tool, cmd, env)
    assert code == 2, (tool, cmd, code, err)
    assert "run_watchdogged.ps1" in err, err
for tool, cmd in ALLOW:
    code, err = run(tool, cmd, env)
    assert code == 0, (tool, cmd, code, err)
print(f"default venv: {len(BLOCK)} blocked, {len(ALLOW)} allowed as expected", flush=True)

# a venv somewhere else, named by CADPARTS_PYTHON
env2 = dict(env, CADPARTS_PYTHON=r"D:\venvs\cq\Scripts\python.exe")
assert run("PowerShell", r"D:\venvs\cq\Scripts\python.exe part.py", env2)[0] == 2
assert run("Bash", "/d/venvs/cq/Scripts/python.exe part.py", env2)[0] == 2
assert run("PowerShell", r"D:\venvs\cq\Scripts\python.exe part.py", env)[0] == 0, "unknown venv must pass"
print("CADPARTS_PYTHON venv: blocked when named, ignored when not", flush=True)

# a broken payload is a visible hook error (exit 1), never a silent pass
r = subprocess.run([sys.executable, "-I", str(HOOK)], input="{not json", capture_output=True, text=True,
                   timeout=30)
assert r.returncode == 1 and "hook error" in r.stderr, (r.returncode, r.stderr)
print("malformed input: exit 1 with an error", flush=True)
print("DONE", flush=True)
