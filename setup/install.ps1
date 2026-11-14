# Copyright 2026 Colin Ezra Wilder. SPDX-License-Identifier: Apache-2.0
# Sets up the cad-parts skill on this PC (Windows 10/11, 64-bit):
#   1. creates the Python venv C:\cadquery-venv (Python 3.14, via uv) and installs the pinned packages,
#   2. installs cq_helpers.py into that venv,
#   3. copies the skill to %USERPROFILE%\.claude\skills\cad-parts (Claude Code's personal skills folder),
#   4. runs the skill's self-test through its watchdog runner.
# Safe to re-run: an existing venv is reused, an existing skill folder is left alone unless -Force.
#
# Run from PowerShell in the folder that holds README.md:
#   powershell -ExecutionPolicy Bypass -File .\setup\install.ps1
param(
    [string]$VenvPath = 'C:\cadquery-venv',
    [string]$SkillsDir = "$env:USERPROFILE\.claude\skills",
    [string]$PythonVersion = '3.14',
    [switch]$Force
)
# No global 'Stop': Windows PowerShell 5.1 can turn uv's progress output (stderr) into errors.
# Native steps are checked by exit code, file steps use -ErrorAction Stop.
$root = Split-Path -Parent $PSScriptRoot
$skillSrc = Join-Path $root 'cad-parts'
$req = Join-Path $PSScriptRoot 'requirements.txt'

function Step($msg) { Write-Host "`n== $msg" -ForegroundColor Cyan }

# 0. uv (Astral's Python installer). Not installed automatically: install it yourself first.
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv -and (Test-Path "$env:USERPROFILE\.local\bin\uv.exe")) { $uv = "$env:USERPROFILE\.local\bin\uv.exe" }
if (-not $uv) {
    Write-Host 'uv is not installed. Install it (official installer, https://docs.astral.sh/uv/), then re-run this:' -ForegroundColor Yellow
    Write-Host '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
    exit 1
}
Write-Host "uv: $uv"

# 1. venv
$py = Join-Path $VenvPath 'Scripts\python.exe'
if (Test-Path $py) {
    Step "venv exists, reusing $VenvPath"
} else {
    Step "creating venv $VenvPath (Python $PythonVersion)"
    & $uv venv $VenvPath --python $PythonVersion --seed
    if ($LASTEXITCODE -ne 0) { Write-Host 'uv venv failed' -ForegroundColor Red; exit 1 }
}
Step 'installing packages (first run downloads a few hundred MB)'
& $uv pip install --python $py -r $req
if ($LASTEXITCODE -ne 0) { Write-Host 'package install failed' -ForegroundColor Red; exit 1 }

# 2. cq_helpers into site-packages
$site = (& $py -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")
if ($LASTEXITCODE -ne 0 -or -not $site) { Write-Host 'could not find the venv site-packages' -ForegroundColor Red; exit 1 }
Copy-Item (Join-Path $skillSrc 'venv-modules\cq_helpers.py') $site.Trim() -Force -ErrorAction Stop
Step "cq_helpers.py -> $($site.Trim())"

# 3. the skill
$dest = Join-Path $SkillsDir 'cad-parts'
if ((Test-Path $dest) -and -not $Force) {
    Step "skill already at $dest, left alone (re-run with -Force to replace it)"
} else {
    if (Test-Path $dest) { Remove-Item $dest -Recurse -Force -ErrorAction Stop }
    New-Item -ItemType Directory -Force $SkillsDir -ErrorAction Stop | Out-Null
    Copy-Item $skillSrc $dest -Recurse -ErrorAction Stop
    # the license travels with the installed copy
    foreach ($f in 'LICENSE', 'NOTICE') { Copy-Item (Join-Path $root $f) $dest -ErrorAction Stop }
    Step "skill copied to $dest"
}

# 4. self-test through the runner, with this venv's Python
Step 'self-test (about 15 s)'
& (Join-Path $dest 'scripts\run_watchdogged.ps1') -Script (Join-Path $dest 'scripts\test_cq_helpers.py') -Python $py -Tail 12
if ($LASTEXITCODE -ne 0) { Write-Host "`nSELF-TEST FAILED (exit $LASTEXITCODE). Full log: $dest\scripts\test_cq_helpers.py.out.txt" -ForegroundColor Red; exit 1 }
Write-Host "`nAll set. Restart Claude Code, then ask it for a part (or type /cad-parts)." -ForegroundColor Green
