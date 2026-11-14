# Copyright 2026 Colin Ezra Wilder. SPDX-License-Identifier: Apache-2.0
# One-shot watchdogged runner for CadQuery scripts (2026-07-15). Runs the script
# under C:\cadquery-venv (or -Python / $env:CADPARTS_PYTHON) inside a Windows job
# object, so the RAM cap and the kill cover the whole process tree.
#
# Why a job object (fixed 2026-09-15): C:\cadquery-venv\Scripts\python.exe is
# a 45 KB uv trampoline that spawns the real interpreter as a CHILD process.
# The old runner polled the trampoline's own working set (always ~0.01 GB), so
# the cap could never fire, and Stop-Process on the trampoline left anything
# the script spawned running. Now:
#   - the trampoline starts suspended and joins the job before it runs, so the
#     interpreter and everything it spawns are born inside the job (no race);
#   - the cap is a kernel limit on the tree's total committed memory: an
#     allocation past it is refused, it cannot overshoot between polls, and the
#     runner then kills the tree (exit 137);
#   - timeout and cap kills use TerminateJobObject, which ends every process
#     in the tree, and KILL_ON_JOB_CLOSE ends it too if this runner dies (tool
#     timeout, closed terminal, Ctrl+C).
# The build always starts without PYTHONOPTIMIZE, so a script's own asserts run (2026-11-14).
# Exit codes: the script's own code on normal exit, 137 on watchdog kill, 2 if
# the script path is missing, 3 if the watchdog could not be armed (the script
# never ran).
#
# Usage:
#   & run_watchdogged.ps1 -Script "C:\path\to\part.py"
#   & run_watchdogged.ps1 -Script "..." -TimeoutSec 600 -MaxRamGB 6   # heavy job, deliberate
#   & run_watchdogged.ps1 -Script "..." -Tail 40      # print only the last 40 stdout lines
#   & run_watchdogged.ps1 -Script "..." -Python "D:\venvs\cq\Scripts\python.exe"   # venv elsewhere
# The full stdout always lands in <script>.out.txt beside the script (the build's run
# log, cited by READMEs). <script>.err.txt is kept only when stderr had
# something in it. The summary line reports wall time so -TimeoutSec can be chosen
# deliberately.
param(
    [Parameter(Mandatory = $true)][string]$Script,
    [ValidateRange(1, 86400)][int]$TimeoutSec = 300,
    [ValidateRange(0.1, 1024)][double]$MaxRamGB = 4,
    [ValidateRange(0, 1000000)][int]$Tail = 0,
    [string]$Python = $(if ($env:CADPARTS_PYTHON) { $env:CADPARTS_PYTHON } else { 'C:\cadquery-venv\Scripts\python.exe' })
)
$py = $Python
if (-not (Test-Path $py)) { Write-Host "WATCHDOG SETUP FAILED: no Python at $py (run setup\install.ps1, or pass -Python)"; exit 3 }
if (-not (Test-Path $Script)) { Write-Host "no such script: $Script"; exit 2 }
$Script = (Resolve-Path $Script).ProviderPath
$out = "$Script.out.txt"
$err = "$Script.err.txt"

if (-not ('CadWatchdog.JobProcess' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace CadWatchdog
{
    // One process tree inside one job object. C# 5 syntax so Windows
    // PowerShell 5.1 can compile it too.
    public sealed class JobProcess : IDisposable
    {
        const uint JOB_OBJECT_LIMIT_JOB_MEMORY = 0x200;
        const uint JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x400;
        const uint JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000;
        const int JobObjectBasicAccountingInformation = 1;
        const int JobObjectAssociateCompletionPortInformation = 7;
        const int JobObjectExtendedLimitInformation = 9;
        const uint JOB_OBJECT_MSG_JOB_MEMORY_LIMIT = 10;
        const uint CREATE_SUSPENDED = 0x4;
        const uint CREATE_NO_WINDOW = 0x08000000;
        const int STARTF_USESTDHANDLES = 0x100;
        const uint GENERIC_READ = 0x80000000, GENERIC_WRITE = 0x40000000;
        const uint CREATE_ALWAYS = 2, OPEN_EXISTING = 3;
        const uint WAIT_TIMEOUT = 0x102;

        [StructLayout(LayoutKind.Sequential)]
        struct BasicLimit
        {
            public long PerProcessUserTimeLimit, PerJobUserTimeLimit;
            public uint LimitFlags;
            public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint PriorityClass, SchedulingClass;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct IoCounters { public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes; }

        [StructLayout(LayoutKind.Sequential)]
        struct ExtendedLimit
        {
            public BasicLimit Basic;
            public IoCounters Io;
            public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct Accounting
        {
            public long TotalUserTime, TotalKernelTime, ThisPeriodTotalUserTime, ThisPeriodTotalKernelTime;
            public uint TotalPageFaultCount, TotalProcesses, ActiveProcesses, TotalTerminatedProcesses;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct PortAssociation { public IntPtr CompletionKey, CompletionPort; }

        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        struct StartupInfo
        {
            public int cb;
            public string lpReserved, lpDesktop, lpTitle;
            public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags;
            public short wShowWindow, cbReserved2;
            public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct ProcessInformation { public IntPtr hProcess, hThread; public int dwProcessId, dwThreadId; }

        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        static extern IntPtr CreateJobObjectW(IntPtr attributes, string name);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool SetInformationJobObject(IntPtr job, int cls, ref ExtendedLimit info, int size);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool SetInformationJobObject(IntPtr job, int cls, ref PortAssociation info, int size);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool QueryInformationJobObject(IntPtr job, int cls, out ExtendedLimit info, int size, IntPtr returned);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool QueryInformationJobObject(IntPtr job, int cls, out Accounting info, int size, IntPtr returned);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool TerminateJobObject(IntPtr job, uint exitCode);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern IntPtr CreateIoCompletionPort(IntPtr file, IntPtr existingPort, UIntPtr key, uint threads);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool GetQueuedCompletionStatus(IntPtr port, out uint bytes, out UIntPtr key, out IntPtr overlapped, uint ms);
        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        static extern bool CreateProcessW(string app, StringBuilder commandLine, IntPtr processAttributes,
            IntPtr threadAttributes, bool inheritHandles, uint flags, IntPtr environment, string cwd,
            ref StartupInfo startup, out ProcessInformation info);
        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        static extern IntPtr CreateFileW(string path, uint access, uint share, IntPtr attributes,
            uint disposition, uint flags, IntPtr template);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool SetHandleInformation(IntPtr handle, uint mask, uint flags);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern uint ResumeThread(IntPtr thread);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool TerminateProcess(IntPtr process, uint exitCode);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern uint WaitForSingleObject(IntPtr handle, uint ms);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool GetExitCodeProcess(IntPtr process, out uint exitCode);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool CloseHandle(IntPtr handle);

        IntPtr job, port, process;
        public int Pid { get; private set; }
        public bool CapHit { get; private set; }

        static void Fail(string what)
        {
            throw new InvalidOperationException(what + " failed, Win32 error " + Marshal.GetLastWin32Error());
        }

        public JobProcess(ulong memoryLimitBytes)
        {
            job = CreateJobObjectW(IntPtr.Zero, null);
            if (job == IntPtr.Zero) Fail("CreateJobObject");
            port = CreateIoCompletionPort(new IntPtr(-1), IntPtr.Zero, UIntPtr.Zero, 1);
            if (port == IntPtr.Zero) Fail("CreateIoCompletionPort");
            PortAssociation assoc = new PortAssociation();
            assoc.CompletionKey = job;
            assoc.CompletionPort = port;
            if (!SetInformationJobObject(job, JobObjectAssociateCompletionPortInformation, ref assoc, Marshal.SizeOf(assoc)))
                Fail("associate completion port");
            // DIE_ON_UNHANDLED_EXCEPTION: a crashing interpreter dies at once
            // instead of hanging on a hidden WER dialog until the timeout.
            ExtendedLimit limit = new ExtendedLimit();
            limit.Basic.LimitFlags = JOB_OBJECT_LIMIT_JOB_MEMORY | JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
                | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            limit.JobMemoryLimit = new UIntPtr(memoryLimitBytes);
            if (!SetInformationJobObject(job, JobObjectExtendedLimitInformation, ref limit, Marshal.SizeOf(limit)))
                Fail("set job limits");
        }

        static IntPtr OpenInheritable(string path, uint access, uint disposition)
        {
            IntPtr h = CreateFileW(path, access, 7, IntPtr.Zero, disposition, 0, IntPtr.Zero);
            if (h == new IntPtr(-1)) Fail("open " + path);
            if (!SetHandleInformation(h, 1, 1)) { CloseHandle(h); Fail("inherit " + path); }
            return h;
        }

        // Start suspended, join the job, then resume: the trampoline cannot
        // spawn the interpreter before it is inside the job.
        public int Start(string commandLine, string cwd, string outPath, string errPath)
        {
            IntPtr hIn = OpenInheritable("NUL", GENERIC_READ, OPEN_EXISTING);
            IntPtr hOut = IntPtr.Zero, hErr = IntPtr.Zero;
            try
            {
                hOut = OpenInheritable(outPath, GENERIC_WRITE, CREATE_ALWAYS);
                hErr = OpenInheritable(errPath, GENERIC_WRITE, CREATE_ALWAYS);
                StartupInfo si = new StartupInfo();
                si.cb = Marshal.SizeOf(si);
                si.dwFlags = STARTF_USESTDHANDLES;
                si.hStdInput = hIn;
                si.hStdOutput = hOut;
                si.hStdError = hErr;
                ProcessInformation pi;
                if (!CreateProcessW(null, new StringBuilder(commandLine), IntPtr.Zero, IntPtr.Zero, true,
                        CREATE_SUSPENDED | CREATE_NO_WINDOW, IntPtr.Zero, cwd, ref si, out pi))
                    Fail("CreateProcess");
                process = pi.hProcess;
                Pid = pi.dwProcessId;
                if (!AssignProcessToJobObject(job, process))
                {
                    int e = Marshal.GetLastWin32Error();
                    TerminateProcess(process, 1);
                    CloseHandle(pi.hThread);
                    throw new InvalidOperationException("AssignProcessToJobObject failed, Win32 error " + e);
                }
                if (ResumeThread(pi.hThread) == uint.MaxValue) { TerminateJobObject(job, 1); Fail("ResumeThread"); }
                CloseHandle(pi.hThread);
                return Pid;
            }
            finally
            {
                CloseHandle(hIn);
                if (hOut != IntPtr.Zero) CloseHandle(hOut);
                if (hErr != IntPtr.Zero) CloseHandle(hErr);
            }
        }

        // True once the launched process has exited (or the wait failed).
        public bool WaitExit(int ms)
        {
            return WaitForSingleObject(process, (uint)ms) != WAIT_TIMEOUT;
        }

        // Drain job notifications; latches CapHit when the kernel refused an
        // allocation that would have pushed the tree past the job memory limit.
        // The API does not formally guarantee message delivery; if one were
        // lost, the kernel limit still holds and only the exit code differs.
        public bool PollCap()
        {
            uint msg;
            UIntPtr key;
            IntPtr overlapped;
            while (GetQueuedCompletionStatus(port, out msg, out key, out overlapped, 0))
                if (msg == JOB_OBJECT_MSG_JOB_MEMORY_LIMIT) CapHit = true;
            return CapHit;
        }

        Accounting Account()
        {
            Accounting a;
            if (!QueryInformationJobObject(job, JobObjectBasicAccountingInformation, out a, Marshal.SizeOf(typeof(Accounting)), IntPtr.Zero))
                Fail("query job accounting");
            return a;
        }

        public int ActiveProcesses { get { return (int)Account().ActiveProcesses; } }
        public int TotalProcesses { get { return (int)Account().TotalProcesses; } }

        public ulong PeakBytes
        {
            get
            {
                ExtendedLimit x;
                if (!QueryInformationJobObject(job, JobObjectExtendedLimitInformation, out x, Marshal.SizeOf(typeof(ExtendedLimit)), IntPtr.Zero))
                    Fail("query job peak memory");
                return x.PeakJobMemoryUsed.ToUInt64();
            }
        }

        public int ExitCode
        {
            get
            {
                uint code;
                if (!GetExitCodeProcess(process, out code)) Fail("GetExitCodeProcess");
                return unchecked((int)code);
            }
        }

        // Kill every process in the tree, then wait for the job to empty.
        public bool KillTree(uint exitCode, int waitMs)
        {
            TerminateJobObject(job, exitCode);
            int until = Environment.TickCount + waitMs;
            while (ActiveProcesses > 0)
            {
                if (Environment.TickCount > until) return false;
                Thread.Sleep(25);
            }
            return true;
        }

        public void Dispose()
        {
            if (process != IntPtr.Zero) { CloseHandle(process); process = IntPtr.Zero; }
            if (port != IntPtr.Zero) { CloseHandle(port); port = IntPtr.Zero; }
            // KILL_ON_JOB_CLOSE: closing the last job handle ends anything left.
            if (job != IntPtr.Zero) { CloseHandle(job); job = IntPtr.Zero; }
        }
    }
}
'@
}

$killed = $null
$note = $null
try {
    $job = [CadWatchdog.JobProcess]::new([uint64]($MaxRamGB * 1GB))
} catch {
    Write-Host "WATCHDOG SETUP FAILED: $($_.Exception.Message)"; exit 3
}
try {
    try {
        $cwd = (Get-Location -PSProvider FileSystem).ProviderPath
        # A PYTHONOPTIMIZE setting would strip every assert a part script uses as a check
        # (bbox asserts, guard formulas). The build starts without it; the caller keeps it.
        $savedOptimize = $env:PYTHONOPTIMIZE
        Remove-Item Env:PYTHONOPTIMIZE -ErrorAction SilentlyContinue
        try {
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            $null = $job.Start("`"$py`" -u `"$Script`"", $cwd, $out, $err)
        } finally {
            if ($null -ne $savedOptimize) { $env:PYTHONOPTIMIZE = $savedOptimize }
        }
    } catch {
        Write-Host "WATCHDOG SETUP FAILED: $($_.Exception.Message)"; exit 3
    }
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while (-not $job.WaitExit(500)) {
        if ($job.PollCap()) { break }
        if ((Get-Date) -gt $deadline) { $killed = "runtime exceeded $TimeoutSec s"; break }
    }
    $elapsed = $sw.Elapsed.TotalSeconds
    # Checked after exit too: a refused allocation often ends the script on
    # its own (MemoryError) before the next poll.
    if ($job.PollCap()) {
        $killed = "tree committed memory hit the $MaxRamGB GB cap (kernel refused the allocation)"
    }
    if ($killed) {
        if (-not $job.KillTree(137, 5000)) { $note = "WARNING: $($job.ActiveProcesses) process(es) still alive 5 s after the kill" }
    } elseif ($job.ActiveProcesses -gt 0) {
        # the launcher can exit a few ms before its interpreter finishes tearing down;
        # give the tree a moment before calling anything a leftover
        $grace = (Get-Date).AddSeconds(2)
        while ($job.ActiveProcesses -gt 0 -and (Get-Date) -lt $grace) { Start-Sleep -Milliseconds 50 }
        if ($job.ActiveProcesses -gt 0) {
            $left = $job.ActiveProcesses
            $null = $job.KillTree(1, 5000)
            $note = "killed $left leftover process(es) still in the job 2 s after the script exited"
        }
    }
    $exitCode = $job.ExitCode
    $peak = $job.PeakBytes
    $procs = $job.TotalProcesses
    $pid0 = $job.Pid
    $capHit = $job.CapHit
} finally {
    $job.Dispose()
}

Write-Host "--- stdout ---"
if (Test-Path $out) {
    $lines = @(Get-Content $out)
    if ($Tail -gt 0 -and $lines.Count -gt $Tail) {
        Write-Host ("(... {0} earlier lines omitted by -Tail {1}; full log: {2})" -f ($lines.Count - $Tail), $Tail, $out)
        $lines | Select-Object -Last $Tail
    } else {
        $lines
    }
}
$errText = $null
if (Test-Path $err) { $errText = Get-Content $err -Raw }
if ([string]::IsNullOrWhiteSpace($errText)) {
    # nothing to keep: no empty .err.txt litter beside the script
    if (Test-Path $err) { Remove-Item $err -Force -ErrorAction SilentlyContinue }
} else {
    Write-Host "--- stderr (kept in $err) ---"
    Write-Host $errText
}
Write-Host ("--- {0:N1} s wall, peak memory {1:N2} GB committed, whole tree ({2} processes, launcher pid {3}); log {4} ---" -f $elapsed, ($peak / 1GB), $procs, $pid0, $out)
if ($capHit) { Write-Host "(Windows counts the refused allocation in that peak; the tree never held more than $MaxRamGB GB)" }
if ($note) { Write-Host $note }
if ($killed) { Write-Host "WATCHDOG KILLED: $killed"; exit 137 }
exit $exitCode
