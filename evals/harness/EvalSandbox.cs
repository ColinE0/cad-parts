// One process tree inside one Windows job object, for the eval harness. Adapted from the
// cad-parts runner's JobProcess (scripts/run_watchdogged.ps1), with stdin read from a file.
// Kernel-enforced committed-memory cap over the whole tree, kill-on-close, suspended start.
using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace EvalSandbox
{
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

        public int Start(string commandLine, string cwd, string inPath, string outPath, string errPath)
        {
            IntPtr hIn = OpenInheritable(inPath, GENERIC_READ, OPEN_EXISTING);
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

        public bool WaitExit(int ms)
        {
            return WaitForSingleObject(process, (uint)ms) != WAIT_TIMEOUT;
        }

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
            if (job != IntPtr.Zero) { CloseHandle(job); job = IntPtr.Zero; }
        }
    }
}
