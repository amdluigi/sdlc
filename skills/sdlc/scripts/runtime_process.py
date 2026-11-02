"""Contained local subprocesses, not an operating-system sandbox."""

import os
import subprocess
import time

PLATFORM = os.name


def supported():
    # Process groups cannot guarantee cleanup after supervisor death.
    return PLATFORM == "nt"


class WindowsProcess:
    containment = "windows-suspended-job"

    def __init__(self, executable, argv, cwd):
        import ctypes as c
        from ctypes import wintypes as w

        self.c, self.w = c, w
        self.api = c.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([c.c_void_p, w.LPCWSTR], w.HANDLE),
            "SetInformationJobObject": ([w.HANDLE, c.c_int, c.c_void_p, w.DWORD], w.BOOL),
            "AssignProcessToJobObject": ([w.HANDLE, w.HANDLE], w.BOOL),
            "TerminateJobObject": ([w.HANDLE, w.UINT], w.BOOL),
            "CloseHandle": ([w.HANDLE], w.BOOL),
            "CreatePipe": ([c.POINTER(w.HANDLE), c.POINTER(w.HANDLE), c.c_void_p, w.DWORD], w.BOOL),
            "SetHandleInformation": ([w.HANDLE, w.DWORD, w.DWORD], w.BOOL),
            "InitializeProcThreadAttributeList": ([c.c_void_p, w.DWORD, w.DWORD, c.POINTER(c.c_size_t)], w.BOOL),
            "UpdateProcThreadAttribute": ([c.c_void_p, w.DWORD, c.c_size_t, c.c_void_p,
                                           c.c_size_t, c.c_void_p, c.c_void_p], w.BOOL),
            "DeleteProcThreadAttributeList": ([c.c_void_p], None),
            "CreateProcessW": ([w.LPCWSTR, w.LPWSTR, c.c_void_p, c.c_void_p, w.BOOL, w.DWORD,
                                c.c_void_p, w.LPCWSTR, c.c_void_p, c.c_void_p], w.BOOL),
            "ResumeThread": ([w.HANDLE], w.DWORD),
            "TerminateProcess": ([w.HANDLE, w.UINT], w.BOOL),
            "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
            "GetExitCodeProcess": ([w.HANDLE, c.POINTER(w.DWORD)], w.BOOL),
            "PeekNamedPipe": ([w.HANDLE, c.c_void_p, w.DWORD, c.c_void_p,
                                c.POINTER(w.DWORD), c.c_void_p], w.BOOL),
            "ReadFile": ([w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p], w.BOOL),
            "QueryInformationJobObject": ([w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p], w.BOOL),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = arguments, result

        class Security(c.Structure):
            _fields_ = [("length", w.DWORD), ("descriptor", c.c_void_p), ("inherit", w.BOOL)]

        class Startup(c.Structure):
            _fields_ = [("cb", w.DWORD), ("reserved", w.LPWSTR), ("desktop", w.LPWSTR),
                        ("title", w.LPWSTR), ("x", w.DWORD), ("y", w.DWORD),
                        ("xsize", w.DWORD), ("ysize", w.DWORD), ("charsx", w.DWORD),
                        ("charsy", w.DWORD), ("fill", w.DWORD), ("flags", w.DWORD),
                        ("show", w.WORD), ("reservedsize", w.WORD), ("reservedptr", c.c_void_p),
                        ("stdin", w.HANDLE), ("stdout", w.HANDLE), ("stderr", w.HANDLE)]

        class StartupEx(c.Structure):
            _fields_ = [("startup", Startup), ("attributes", c.c_void_p)]

        class ProcessInfo(c.Structure):
            _fields_ = [("process", w.HANDLE), ("thread", w.HANDLE),
                        ("pid", w.DWORD), ("tid", w.DWORD)]

        class BasicLimits(c.Structure):
            _fields_ = [("processTime", c.c_int64), ("jobTime", c.c_int64), ("flags", w.DWORD),
                        ("minWorkingSet", c.c_size_t), ("maxWorkingSet", c.c_size_t),
                        ("activeProcessLimit", w.DWORD), ("affinity", c.c_size_t),
                        ("priorityClass", w.DWORD), ("schedulingClass", w.DWORD)]

        class IoCounters(c.Structure):
            _fields_ = [(name, c.c_uint64) for name in
                        ("readOps", "writeOps", "otherOps", "readBytes", "writeBytes", "otherBytes")]

        class ExtendedLimits(c.Structure):
            _fields_ = [("basic", BasicLimits), ("io", IoCounters),
                        ("processMemory", c.c_size_t), ("jobMemory", c.c_size_t),
                        ("peakProcessMemory", c.c_size_t), ("peakJobMemory", c.c_size_t)]

        self.job = self.process = self.reader = None
        writer, input_reader, input_writer, thread, attributes = w.HANDLE(), w.HANDLE(), w.HANDLE(), None, None
        attributes_initialized = False
        info = ProcessInfo()
        try:
            self.job = self.api.CreateJobObjectW(None, None)
            self.require(self.job)
            limits = ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, no breakaway.
            self.require(self.api.SetInformationJobObject(self.job, 9, c.byref(limits), c.sizeof(limits)))
            security = Security(c.sizeof(Security), None, True)
            reader = w.HANDLE()
            self.require(self.api.CreatePipe(c.byref(reader), c.byref(writer), c.byref(security), 0))
            self.reader = reader.value
            self.require(self.api.SetHandleInformation(self.reader, 1, 0))
            self.require(self.api.CreatePipe(c.byref(input_reader), c.byref(input_writer), c.byref(security), 0))
            self.require(self.api.SetHandleInformation(input_writer, 1, 0))
            size = c.c_size_t()
            self.api.InitializeProcThreadAttributeList(None, 1, 0, c.byref(size))
            attributes = c.create_string_buffer(size.value)
            self.require(self.api.InitializeProcThreadAttributeList(attributes, 1, 0, c.byref(size)))
            attributes_initialized = True
            handles = (w.HANDLE * 2)(writer.value, input_reader.value)
            self.require(self.api.UpdateProcThreadAttribute(
                attributes, 0, 0x20002, handles, c.sizeof(handles), None, None))
            startup = StartupEx()
            startup.startup.cb = c.sizeof(startup)
            startup.startup.flags = 0x100  # STARTF_USESTDHANDLES
            startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = input_reader, writer, writer
            startup.attributes = c.cast(attributes, c.c_void_p)
            command = c.create_unicode_buffer(subprocess.list2cmdline([executable, *argv]))
            # The first instruction cannot run before successful job assignment.
            self.require(self.api.CreateProcessW(executable, command, None, None, True,
                                                0x4 | 0x80000 | 0x08000000, None, cwd,
                                                c.byref(startup), c.byref(info)))
            self.process, thread = info.process, info.thread
            self.require(self.api.AssignProcessToJobObject(self.job, self.process))
            if self.api.ResumeThread(thread) == 0xFFFFFFFF:
                raise c.WinError(c.get_last_error())
        except BaseException:
            if self.process:
                self.api.TerminateProcess(self.process, 1)
            self.close()
            raise
        finally:
            for handle in (writer.value, input_reader.value, input_writer.value, thread):
                if handle:
                    self.api.CloseHandle(handle)
            if attributes_initialized:
                self.api.DeleteProcThreadAttributeList(attributes)

    def require(self, result):
        if not result:
            raise self.c.WinError(self.c.get_last_error())

    def read(self):
        available = self.w.DWORD()
        if not self.api.PeekNamedPipe(self.reader, None, 0, None, self.c.byref(available), None):
            if self.c.get_last_error() == 109:
                return b""
            self.require(False)
        if not available.value:
            return b""
        buffer = self.c.create_string_buffer(min(4096, available.value))
        count = self.w.DWORD()
        self.require(self.api.ReadFile(self.reader, buffer, len(buffer), self.c.byref(count), None))
        return buffer.raw[:count.value]

    def poll(self):
        waited = self.api.WaitForSingleObject(self.process, 0)
        if waited == 258:
            return None
        if waited != 0:
            self.require(False)
        code = self.w.DWORD()
        self.require(self.api.GetExitCodeProcess(self.process, self.c.byref(code)))
        return code.value

    def close(self):
        error = None
        if self.job:
            if not self.api.TerminateJobObject(self.job, 1):
                error = OSError("job termination failed")
            # JOBOBJECT_BASIC_ACCOUNTING_INFORMATION: four LARGE_INTEGERs then four DWORDs.
            accounting = self.c.create_string_buffer(48)
            deadline = time.monotonic() + 5
            while True:
                if not self.api.QueryInformationJobObject(self.job, 1, accounting, len(accounting), None):
                    error = OSError("job termination observation unavailable")
                    break
                active = self.w.DWORD.from_buffer(accounting, 40).value
                if active == 0:
                    break
                if time.monotonic() >= deadline:
                    error = OSError("job descendants remain unconfirmed")
                    break
                time.sleep(.01)
            if not self.api.CloseHandle(self.job):
                error = OSError("job handle close unavailable")
            self.job = None
        if self.process:
            if self.api.WaitForSingleObject(self.process, 5000) != 0:
                error = OSError("process termination remains unconfirmed")
            self.api.CloseHandle(self.process)
            self.process = None
        if self.reader:
            self.api.CloseHandle(self.reader)
            self.reader = None
        if error is not None:
            raise error


def run(command, guard):
    """Return bounded in-memory text plus metadata; always terminate descendants."""
    if not supported():
        raise OSError("owner-death process containment unavailable")
    guard()
    try:
        child = WindowsProcess(command["executable"], command["argv"], command["cwd"])
    except (FileNotFoundError, NotADirectoryError):
        return {"output": "", "evidence": {"status": "spawn-failed", "exitCode": None,
                "outputBytes": 0, "containment": "unavailable"}}
    except AttributeError as error:
        raise OSError("native containment API unavailable") from error
    output = bytearray()
    status, code = "unknown", None
    deadline = time.monotonic() + command["timeoutMs"] / 1000
    try:
        while True:
            guard()
            chunk = child.read()
            remaining = command["maxOutputBytes"] - len(output)
            output.extend(chunk[:remaining])
            if len(chunk) > remaining:
                status = "output-limit"
                break
            code = child.poll()
            if code is not None and not chunk:
                status = "passed" if code == 0 else "nonzero"
                break
            if time.monotonic() >= deadline:
                status = "timeout"
                break
            if not chunk:
                time.sleep(.02)
    finally:
        child.close()
    text = bytes(output).decode("utf-8", errors="replace").encode("utf-8")
    text = text[:command["maxOutputBytes"]].decode("utf-8", errors="ignore")
    return {"output": text,
            "evidence": {"status": status, "exitCode": code,
                         "outputBytes": len(output), "containment": child.containment}}
