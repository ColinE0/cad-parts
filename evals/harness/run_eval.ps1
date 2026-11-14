# Runs ONE cad-parts eval through headless Claude Code, isolated, inside a Windows job object.
#
#   pwsh -File run_eval.ps1 -Config fable52-high -Arm baseline -EvalId 3
#
# Isolation: --safe-mode (no user CLAUDE.md, skills, plugins, hooks, MCP), a fresh working
# folder per run, no session persistence, web tools off, and every CLAUDE*/ANTHROPIC* variable
# from the calling session stripped. The whole process tree (claude.exe plus every Python it
# starts) sits in one job object with a committed-memory cap and a wall-clock timeout, so a
# runaway CAD op in a no-skill run cannot take the machine down.
#
# Arms: "skill" gets the skill-under-test folder (read-only) named in an appended system prompt,
# its runner pointed at the eval venv, and the skill's cq_helpers on PYTHONPATH. "baseline" gets
# the same environment note and nothing else. The user prompt is the eval prompt verbatim plus an
# "Attached:" line for its input files.
#
# Writes runs\<config>\<arm>\eval-<id>\ (the agent's working folder) and
# logs\<config>.<arm>.eval-<id>.{prompt.txt,system.txt,stream.jsonl,err.txt,status.json}.
param(
    [Parameter(Mandatory = $true)][ValidateSet('fable51-medium', 'fable52-high')][string]$Config,
    [Parameter(Mandatory = $true)][ValidateSet('skill', 'baseline')][string]$Arm,
    [Parameter(Mandatory = $true)][int]$EvalId,
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [int]$TimeoutMin = 45,
    [double]$MaxRamGB = 12,
    [double]$BudgetUsd = 10,
    [string]$ClaudeExe
)
$ErrorActionPreference = 'Stop'

$models = @{
    'fable51-medium' = @{ model = 'claude-fable-5-1'; effort = 'medium' }
    'fable52-high'   = @{ model = 'claude-fable-5-2'; effort = 'high' }
}
$model = $models[$Config].model
$effort = $models[$Config].effort

if (-not $ClaudeExe) {
    # The desktop app's bundled CLI (2.1.325 on 2026-11-14); the PATH copies are too old for Fable 5.x.
    $ClaudeExe = Get-ChildItem "$env:LOCALAPPDATA\Claude-Data\*\claude-code\*\*\claude.exe" -ErrorAction SilentlyContinue |
        Sort-Object { [version](Split-Path (Split-Path $_.DirectoryName -Parent) -Leaf) } -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $ClaudeExe -or -not (Test-Path $ClaudeExe)) { throw "no claude.exe found (pass -ClaudeExe)" }

$specDir = if (Test-Path (Join-Path $Root 'spec\evals.json')) { Join-Path $Root 'spec' } else { $Root }
$skillDir = Join-Path $Root 'skill-under-test\cad-parts'
$venvDir = Join-Path $Root 'venv'
$venvPy = Join-Path $venvDir 'Scripts\python.exe'
$runDir = Join-Path $Root "runs\$Config\$Arm\eval-$EvalId"
$logDir = Join-Path $Root 'logs'
$tag = "$Config.$Arm.eval-$EvalId"
$logBase = Join-Path $logDir $tag

$spec = Get-Content (Join-Path $specDir 'evals.json') -Raw | ConvertFrom-Json
$eval = $spec.evals | Where-Object { $_.id -eq $EvalId }
if (-not $eval) { throw "no eval $EvalId in spec\evals.json" }
if ($Arm -eq 'skill' -and -not (Test-Path (Join-Path $skillDir 'SKILL.md'))) { throw "no skill under test at $skillDir" }
if (Test-Path $runDir) { throw "$runDir already exists; move it aside to re-run" }

New-Item -ItemType Directory -Force $runDir, $logDir | Out-Null
$attached = @()
foreach ($f in $eval.files) {
    $src = Join-Path $specDir $f
    $dst = Join-Path $runDir $f
    New-Item -ItemType Directory -Force (Split-Path $dst -Parent) | Out-Null
    Copy-Item $src $dst
    $attached += $f
}

# The user turn: the eval prompt verbatim, plus the attachment list.
$prompt = $eval.prompt
if ($attached.Count) { $prompt += "`n`nAttached: " + ($attached -join ', ') }
Set-Content -Path "$logBase.prompt.txt" -Value $prompt -Encoding utf8NoBOM

# Environment note, identical for both arms; the skill arm adds where the skill is.
$system = @"
Environment for this task: your working folder is $runDir. Keep everything you create inside it.
CadQuery is installed in the Python venv at $venvDir; run Python as $venvPy and do not install packages.
The user is away and cannot answer questions during this task. If you would normally stop to ask
something, write the question and the answer you are assuming to QUESTIONS.md in the working folder,
then carry on.
"@
if ($Arm -eq 'skill') {
    $system += @"

The cad-parts skill is installed for this task at $skillDir. Read $skillDir\SKILL.md before doing
anything else and follow it. Wherever it names %USERPROFILE%\.claude\skills\cad-parts, use $skillDir
instead. Its runner already uses the venv above (CADPARTS_PYTHON is set).
"@
}
Set-Content -Path "$logBase.system.txt" -Value $system -Encoding utf8NoBOM

# Child environment: nothing from the calling Claude session leaks into the run.
Get-ChildItem env: | Where-Object { $_.Name -match '^(CLAUDE|ANTHROPIC)' } | ForEach-Object { Remove-Item "env:$($_.Name)" }
Remove-Item env:PYTHONPATH -ErrorAction SilentlyContinue
Remove-Item env:CADPARTS_PYTHON -ErrorAction SilentlyContinue
$env:DISABLE_AUTOUPDATER = '1'
if ($Arm -eq 'skill') {
    $env:CADPARTS_PYTHON = $venvPy
    $env:PYTHONPATH = Join-Path $skillDir 'venv-modules'
}

$argv = @(
    '-p', '--model', $model, '--effort', $effort, '--safe-mode', '--no-session-persistence',
    '--permission-mode', 'auto', '--output-format', 'stream-json', '--verbose',
    '--max-budget-usd', "$BudgetUsd", '--disallowedTools', 'WebSearch,WebFetch',
    '--append-system-prompt-file', "$logBase.system.txt"
)
if ($Arm -eq 'skill') { $argv += @('--add-dir', $skillDir) }
$cmd = '"' + $ClaudeExe + '" ' + (($argv | ForEach-Object { if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } }) -join ' ')

if (-not ('EvalSandbox.JobProcess' -as [type])) {
    Add-Type -Path (Join-Path $PSScriptRoot 'EvalSandbox.cs')
}
$job = [EvalSandbox.JobProcess]::new([uint64]($MaxRamGB * 1GB))
$started = Get-Date
$killed = $null
try {
    $null = $job.Start($cmd, $runDir, "$logBase.prompt.txt", "$logBase.stream.jsonl", "$logBase.err.txt")
    $deadline = $started.AddMinutes($TimeoutMin)
    while (-not $job.WaitExit(2000)) {
        if ($job.PollCap()) { break }
        if ((Get-Date) -gt $deadline) { $killed = "timeout after $TimeoutMin min"; break }
    }
    if ($job.PollCap()) { $killed = "memory cap $MaxRamGB GB hit (kernel refused an allocation)" }
    if ($killed) { $null = $job.KillTree(137, 10000) }
    elseif ($job.ActiveProcesses -gt 0) { Start-Sleep -Seconds 2; if ($job.ActiveProcesses -gt 0) { $null = $job.KillTree(1, 10000) } }
    $exitCode = $job.ExitCode
    $peakGB = [math]::Round($job.PeakBytes / 1GB, 2)
    $procs = $job.TotalProcesses
} finally {
    $job.Dispose()
}
$finished = Get-Date

# The stream's last "result" event carries cost, turns and usage.
$result = $null
if (Test-Path "$logBase.stream.jsonl") {
    foreach ($line in [System.IO.File]::ReadLines("$logBase.stream.jsonl")) {
        if ($line -match '"type":"result"') {
            $o = $line | ConvertFrom-Json
            if ($o.type -eq 'result') { $result = $o }
        }
    }
}
$status = [ordered]@{
    config = $Config; arm = $Arm; eval = $EvalId; model = $model; effort = $effort
    claude_exe = $ClaudeExe; started = $started.ToString('s'); finished = $finished.ToString('s')
    wall_min = [math]::Round(($finished - $started).TotalMinutes, 2)
    exit_code = $exitCode; killed = $killed; peak_committed_gb = $peakGB; processes = $procs
    is_error = $result.is_error; subtype = $result.subtype; num_turns = $result.num_turns
    cost_usd = $result.total_cost_usd; usage = $result.usage
}
$status | ConvertTo-Json -Depth 6 | Set-Content -Path "$logBase.status.json" -Encoding utf8NoBOM
Write-Host ("{0}: exit {1}, {2} min, {3} turns, `${4}, peak {5} GB{6}" -f $tag, $exitCode, $status.wall_min, $status.num_turns, $status.cost_usd, $peakGB, $(if ($killed) { ", KILLED: $killed" } else { '' }))
