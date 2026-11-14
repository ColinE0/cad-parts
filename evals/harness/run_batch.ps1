# Runs a list of evals, at most -Parallel at a time, each in its own pwsh running run_eval.ps1.
#   pwsh -File run_batch.ps1 -Jobs fable52-high:baseline:1,fable52-high:baseline:2 -Parallel 3
param(
    [Parameter(Mandatory = $true)][string[]]$Jobs,
    [int]$Parallel = 3
)
$pwsh = (Get-Process -Id $PID).Path
$runner = Join-Path $PSScriptRoot 'run_eval.ps1'
$logDir = Join-Path (Split-Path -Parent $PSScriptRoot) 'logs'
$queue = [System.Collections.Generic.Queue[string]]::new([string[]]($Jobs | ForEach-Object { $_ -split ',' } | Where-Object { $_ }))
$running = @()
$t0 = Get-Date
while ($queue.Count -or $running.Count) {
    while ($queue.Count -and $running.Count -lt $Parallel) {
        $j = $queue.Dequeue()
        $c, $a, $e = $j -split ':'
        $out = Join-Path $logDir "$c.$a.eval-$e.harness.txt"
        $p = Start-Process -FilePath $pwsh -ArgumentList @('-NoProfile', '-File', $runner, '-Config', $c, '-Arm', $a, '-EvalId', $e) `
            -RedirectStandardOutput $out -RedirectStandardError "$out.err" -WindowStyle Hidden -PassThru
        $running += [pscustomobject]@{ Job = $j; Proc = $p; Out = $out }
        Write-Host ("{0:HH:mm:ss} started {1}" -f (Get-Date), $j)
        Start-Sleep -Seconds 5   # stagger CLI start-up
    }
    Start-Sleep -Seconds 10
    foreach ($r in @($running)) {
        if ($r.Proc.HasExited) {
            $running = @($running | Where-Object { $_ -ne $r })
            $line = if (Test-Path $r.Out) { (Get-Content $r.Out | Select-Object -Last 1) } else { '(no output)' }
            Write-Host ("{0:HH:mm:ss} done    {1}  {2}" -f (Get-Date), $r.Job, $line)
        }
    }
}
Write-Host ("batch finished in {0:N1} min" -f ((Get-Date) - $t0).TotalMinutes)
