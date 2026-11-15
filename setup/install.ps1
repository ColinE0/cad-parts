# Copyright 2026 Colin Ezra Wilder. SPDX-License-Identifier: Apache-2.0
# Sets up or updates the cad-parts skill on this PC (Windows 10/11, 64-bit):
#   1. decides what happens to an already installed skill BEFORE changing anything,
#   2. creates (or reuses) the Python venv C:\cadquery-venv (Python 3.14, via uv) and installs the
#      pinned packages,
#   3. installs the skill to %USERPROFILE%\.claude\skills\cad-parts and its cq_helpers.py into the
#      venv, always together, so the skill and its helpers are never from different versions,
#   4. runs the skill's self-test through its watchdog runner.
# Re-running is safe. If the installed skill already matches this copy, it only refreshes the
# packages and re-tests. If it differs (an older version, or one you edited, for example with your
# parts folder written into SKILL.md), nothing is changed unless you pass -Force; then the old skill
# folder is moved to %USERPROFILE%\.claude\cad-parts-backups\ and skill and helpers are updated
# together.
#
# Run from PowerShell in the folder that holds README.md:
#   powershell -ExecutionPolicy Bypass -File .\setup\install.ps1
#   powershell -ExecutionPolicy Bypass -File .\setup\install.ps1 -Force     # update an existing install
# A venv somewhere else: add -VenvPath D:\venvs\cq, and set CADPARTS_PYTHON to its python.exe so the
# runner finds it.
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
$dest = Join-Path $SkillsDir 'cad-parts'
$version = (Get-Content (Join-Path $skillSrc 'VERSION') -ErrorAction Stop | Select-Object -First 1).Trim()

function Step($msg) { Write-Host "`n== $msg" -ForegroundColor Cyan }

# Every file's relative path and SHA-256, leaving out what the installer adds (LICENSE, NOTICE)
# and what runs leave behind (run logs, bytecode caches). Equal digests = the same skill.
function Get-SkillDigest([string]$dir) {
    $base = (Resolve-Path $dir).ProviderPath.TrimEnd('\')
    $files = Get-ChildItem $base -Recurse -File | Where-Object {
        $_.Name -notin @('LICENSE', 'NOTICE') -and $_.Name -notlike '*.out.txt' -and
        $_.Name -notlike '*.err.txt' -and $_.FullName -notmatch '\\__pycache__\\' }
    $lines = foreach ($f in $files) {
        $f.FullName.Substring($base.Length).ToLowerInvariant() + ' ' + (Get-FileHash $f.FullName -Algorithm SHA256).Hash
    }
    ($lines | Sort-Object) -join "`n"
}

# 1. an installed skill: decide first, so a stop here leaves everything as it was
$action = 'install'
$installed = $null
if (Test-Path $dest) {
    $installed = 'unversioned'
    if (Test-Path (Join-Path $dest 'VERSION')) {
        $installed = (Get-Content (Join-Path $dest 'VERSION') | Select-Object -First 1).Trim()
    }
    if ((Get-SkillDigest $dest) -eq (Get-SkillDigest $skillSrc)) {
        $action = 'same'
    } elseif (-not $Force) {
        Write-Host "A different cad-parts skill is already installed at $dest" -ForegroundColor Yellow
        Write-Host "  installed: $installed    this copy: $version"
        Write-Host '  (an older version, or one that was edited; a parts folder written into SKILL.md counts)'
        Write-Host 'Nothing was changed. To update the skill and its helpers together, re-run with -Force.'
        Write-Host "The installed folder will be kept as a backup in $(Join-Path (Split-Path $SkillsDir -Parent) 'cad-parts-backups')."
        exit 1
    } else {
        $action = 'update'
    }
}

# 2. uv (Astral's Python installer). Not installed automatically: install it yourself first.
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv -and (Test-Path "$env:USERPROFILE\.local\bin\uv.exe")) { $uv = "$env:USERPROFILE\.local\bin\uv.exe" }
if (-not $uv) {
    Write-Host 'uv is not installed. Install it (official installer, https://docs.astral.sh/uv/), then re-run this:' -ForegroundColor Yellow
    Write-Host '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
    exit 1
}
Write-Host "uv: $uv"
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
$site = (& $py -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")
if ($LASTEXITCODE -ne 0 -or -not $site) { Write-Host 'could not find the venv site-packages' -ForegroundColor Red; exit 1 }
$site = $site.Trim()

# 3. the skill and its helpers, always together
if ($action -eq 'same') {
    Step "skill $version already installed at $dest"
} else {
    if ($action -eq 'update') {
        $backupRoot = Join-Path (Split-Path $SkillsDir -Parent) 'cad-parts-backups'
        New-Item -ItemType Directory -Force $backupRoot -ErrorAction Stop | Out-Null
        $backup = Join-Path $backupRoot ("cad-parts-{0}-{1}" -f $installed, (Get-Date -Format 'yyyyMMdd-HHmmss'))
        Move-Item $dest $backup -ErrorAction Stop
        Step "old skill ($installed) moved to $backup"
    }
    New-Item -ItemType Directory -Force $SkillsDir -ErrorAction Stop | Out-Null
    Copy-Item $skillSrc $dest -Recurse -ErrorAction Stop
    # the license travels with the installed copy
    foreach ($f in 'LICENSE', 'NOTICE') { Copy-Item (Join-Path $root $f) $dest -ErrorAction Stop }
    Step "skill $version installed at $dest"
}
Copy-Item (Join-Path $dest 'venv-modules\cq_helpers.py') $site -Force -ErrorAction Stop
Step "cq_helpers.py ($version) -> $site"

# 4. self-test through the runner, with this venv's Python
Step 'self-test (about 15 s)'
& (Join-Path $dest 'scripts\run_watchdogged.ps1') -Script (Join-Path $dest 'scripts\test_cq_helpers.py') -Python $py -Tail 12
if ($LASTEXITCODE -ne 0) { Write-Host "`nSELF-TEST FAILED (exit $LASTEXITCODE). Full log: $dest\scripts\test_cq_helpers.py.out.txt" -ForegroundColor Red; exit 1 }
if ($VenvPath -ne 'C:\cadquery-venv') {
    Write-Host "`nThe venv is not at the default C:\cadquery-venv: set CADPARTS_PYTHON to $py so the runner finds it." -ForegroundColor Yellow
}
Write-Host "`nRecommended: register $dest\hooks\require_runner.py as a Claude Code hook so the runner"
Write-Host 'becomes a rule (README, "Making the runner a rule").'
Write-Host "`nAll set (cad-parts $version). Restart Claude Code, then ask it for a part (or type /cad-parts)." -ForegroundColor Green
