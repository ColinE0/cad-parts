# Copyright 2026 Colin Ezra Wilder. SPDX-License-Identifier: Apache-2.0
"""Claude Code PreToolUse hook: run the CadQuery venv's Python only through the watchdogged runner.

The runner's memory cap and timeout only cover what it launches. SKILL.md says every script in the
venv goes through it, but that is an instruction; this hook makes it a rule. Registered for the Bash
and PowerShell tools, it reads the command Claude is about to run and blocks it (exit 2, reason sent
back to Claude) when a segment starts the venv's interpreter directly:

    C:\\cadquery-venv\\Scripts\\python.exe part.py          blocked
    & $py -c "import cadquery"   ($py set to that path)   blocked
    & ...\\run_watchdogged.ps1 -Script part.py              allowed: the runner
    ...\\python.exe part.py  # run_watchdogged.ps1          blocked: the name is not the program
    powershell -Command "& ...\\python.exe part.py"         blocked: nested shells are read too
    C:\\cadquery-venv\\Scripts\\python.exe -m pip install x  allowed: package management
    Copy-Item cq_helpers.py C:\\cadquery-venv\\Lib\\...      allowed: the path is only an argument

The venv is C:\\cadquery-venv, plus the interpreter in CADPARTS_PYTHON when that is set. Pure
standard library, so it starts fast; an internal error exits 1 (a visible, non-blocking hook error),
never silently 0. Register it in ~/.claude/settings.json (see the README, "Make the runner a rule").
"""
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_VENV = r"C:\cadquery-venv"
RUNNER = Path(__file__).resolve().parent.parent / "scripts" / "run_watchdogged.ps1"
ENV_REF = r"(?:\$env:CADPARTS_PYTHON\b|%CADPARTS_PYTHON%|\$\{?CADPARTS_PYTHON\}?)"
ALLOWED_ARGS = re.compile(r"""^(?:-m\s+(?:pip|ensurepip)\b|--version\b|-V{1,2}\b)""")
# words that run the next word as a program: PowerShell's call operators, cmd, bash wrappers
LAUNCHERS = re.compile(r"""^(?:&|\.|call\b|cmd(?:\.exe)?\s+/[cks]\b|exec\b|nohup\b|time\b|command\b)\s*""", re.I)
ENV_PREFIX = re.compile(r"""^(?:[A-Za-z_]\w*=(?:"[^"]*"|'[^']*'|\S*)\s+)+""")
# the first word of a segment: a quoted path or a bare one
HEAD_TOKEN = re.compile(r"""^(?:"([^"]*)"|'([^']*)'|(\S+))""")
# powershell/pwsh -File <script>: the runner launched through a fresh PowerShell
PS_FILE = re.compile(r"""^(?:powershell|pwsh)(?:\.exe)?\s+(?:-(?!file\b)\S+\s+(?:(?!-)\S+\s+)?)*-file\s+""", re.I)
# a shell handed a command string: powershell -Command "...", bash -c "...", sh -c '...'
NESTED = re.compile(r"""^(?:powershell|pwsh|bash|sh|zsh)(?:\.exe)?\s+"""
                    r"""(?:-(?!command\b|[a-z]*c\b)\S+\s+(?:(?!-)\S+\s+)?)*-(?:command|[a-z]*c)\s+(.*)$""",
                    re.I | re.S)
PIP_ARGS = re.compile(r"""-ArgumentList\s+["']?-m\s+(?:pip|ensurepip)\b""", re.I)


def venv_roots():
    roots = [DEFAULT_VENV]
    custom = os.environ.get("CADPARTS_PYTHON")
    if custom:
        p = Path(custom)
        roots.append(str(p.parent.parent if p.parent.name.lower() == "scripts" else p.parent))
    return roots


def path_pattern(root):
    """One venv's interpreter in Windows (C:\\x or C:/x) or Git Bash (/c/x) spelling."""
    drive, rest = os.path.splitdrive(root)
    parts = [re.escape(x) for x in re.split(r"[\\/]+", rest) if x]
    head = rf"(?:{re.escape(drive[0])}:|/{re.escape(drive[0])})" if drive else ""
    return head + r"[\\/]+" + r"[\\/]+".join(parts) + r"[\\/]+scripts[\\/]+pythonw?(?:\.exe)?(?![\w.])"


def segments(command):
    """Split a command line into the pieces the shell runs one after another or piped."""
    text = command.replace("&&", "\n").replace("||", "\n")
    return [s.strip() for s in re.split(r"[\n;|]", text) if s.strip()]


def strip_launchers(seg):
    s = ENV_PREFIX.sub("", seg)
    while True:
        m = LAUNCHERS.match(s)
        if not m:
            return s
        s = s[m.end():]


def launches_runner(s):
    """True only when the program this segment starts is run_watchdogged.ps1 itself (called
    directly, or as powershell -File), not when the name merely appears in an argument or comment."""
    m = PS_FILE.match(s)
    if m:
        s = s[m.end():]
    t = HEAD_TOKEN.match(s)
    if not t:
        return False
    word = next(g for g in t.groups() if g is not None)
    return re.split(r"[\\/]", word)[-1].lower() == "run_watchdogged.ps1"


def violations(command, depth=0):
    interp = "(?:" + "|".join(path_pattern(r) for r in venv_roots()) + "|" + ENV_REF + ")"
    head_re = re.compile(r"""^["']?""" + interp + r"""["']?(?=\s|$)""", re.I)
    # variables pointed at the interpreter: $py = "C:\...\python.exe" (PowerShell), PY=... (bash)
    aliases = set()
    for m in re.finditer(r"""\$(\w+)\s*=\s*["']?""" + interp, command, re.I):
        aliases.add(m.group(1).lower())
    for m in re.finditer(r"""(?:^|[\s;&|(])([A-Za-z_]\w*)=["']?""" + interp, command, re.I):
        aliases.add(m.group(1).lower())
    alias_re = None
    if aliases:
        names = "|".join(re.escape(a) for a in sorted(aliases))
        alias_re = re.compile(r"""^["']?\$\{?(?:""" + names + r""")\}?["']?(?=\s|$)""", re.I)
    found = []
    for seg in segments(command):
        s = strip_launchers(seg)
        if launches_runner(s):
            continue                      # the runner, whatever Python it is handed
        nested = NESTED.match(s)
        if nested and depth < 3:          # look inside the command string a new shell is given
            inner = nested.group(1).strip().strip("\"'")
            if violations(inner, depth + 1):
                found.append(seg)
            continue
        if re.match(r"(?i)start-process\b", s) and re.search(interp, s, re.I) and not PIP_ARGS.search(s):
            found.append(seg)
            continue
        if re.match(r"(?i)uv\s+run\b", s) and re.search(interp, s, re.I):
            found.append(seg)
            continue
        m = head_re.match(s) or (alias_re.match(s) if alias_re else None)
        if not m:
            continue                      # the interpreter, if named at all, is only an argument
        if ALLOWED_ARGS.match(s[m.end():].strip()):
            continue
        found.append(seg)
    return found


def main():
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    if data.get("tool_name") not in ("Bash", "PowerShell"):
        return 0
    command = (data.get("tool_input") or {}).get("command") or ""
    bad = violations(command)
    if not bad:
        return 0
    print("Blocked by the cad-parts hook: this starts the CadQuery venv's Python outside the "
          "watchdogged runner, so no memory cap or timeout covers it.", file=sys.stderr)
    for seg in bad[:3]:
        print(f"  - {seg[:160]}", file=sys.stderr)
    print(f"Run the script through the runner instead (save inline code as a .py file first):\n"
          f"  & \"{RUNNER}\" -Script <file.py> -Tail 40\n"
          "Allowed directly: -m pip ..., --version.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # a broken guard must be visible, not silently pass
        print(f"cad-parts require_runner hook error: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
