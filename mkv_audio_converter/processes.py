"""Windows process containment and bounded, cross-platform pipe readers."""
from __future__ import annotations

from contextlib import contextmanager
import os
import queue
import subprocess
import sys
import threading

_dll_lock = threading.Lock()


@contextmanager
def external_dll_search():
    """Do not pass PyInstaller's Qt DLL directory to MKVToolNix's own runtime."""
    if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
        yield
        return
    import ctypes
    with _dll_lock:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
        kernel.SetDllDirectoryW.restype = ctypes.c_int
        if not kernel.SetDllDirectoryW(None):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            yield
        finally:
            if not kernel.SetDllDirectoryW(str(sys._MEIPASS)):
                raise ctypes.WinError(ctypes.get_last_error())


def child_environment(env):
    env = dict(env)
    if getattr(sys, 'frozen', False):
        root = os.path.normcase(os.path.abspath(sys._MEIPASS))
        def bundled(path):
            path = os.path.normcase(os.path.abspath(path))
            return path == root or path.startswith(root + os.sep)
        env['PATH'] = os.pathsep.join(p for p in env.get('PATH', '').split(os.pathsep) if p and not bundled(p))
        if sys.platform != 'win32':
            if 'LD_LIBRARY_PATH_ORIG' in env:
                env['LD_LIBRARY_PATH'] = env['LD_LIBRARY_PATH_ORIG']
            else:
                env.pop('LD_LIBRARY_PATH', None)
    return env


class WindowsJob:
    """Close the job to kill all assigned processes, including descendants."""
    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w
        class Basic(c.Structure):
            _fields_ = [('ProcessTime', c.c_longlong), ('JobTime', c.c_longlong),
                        ('LimitFlags', w.DWORD), ('MinWorking', c.c_size_t), ('MaxWorking', c.c_size_t),
                        ('ActiveLimit', w.DWORD), ('Affinity', c.c_size_t), ('Priority', w.DWORD), ('Scheduling', w.DWORD)]
        class IO(c.Structure):
            _fields_ = [(name, c.c_ulonglong) for name in ('ReadOps', 'WriteOps', 'OtherOps', 'ReadBytes', 'WriteBytes', 'OtherBytes')]
        class Extended(c.Structure):
            _fields_ = [('Basic', Basic), ('IO', IO), ('ProcessMemory', c.c_size_t), ('JobMemory', c.c_size_t),
                        ('PeakProcessMemory', c.c_size_t), ('PeakJobMemory', c.c_size_t)]
        self.c = c
        self.api = c.WinDLL('kernel32', use_last_error=True)
        for name, args, result in (
            ('CreateJobObjectW', [c.c_void_p, w.LPCWSTR], w.HANDLE),
            ('SetInformationJobObject', [w.HANDLE, c.c_int, c.c_void_p, w.DWORD], w.BOOL),
            ('AssignProcessToJobObject', [w.HANDLE, w.HANDLE], w.BOOL),
            ('CloseHandle', [w.HANDLE], w.BOOL),
        ):
            fn = getattr(self.api, name)
            fn.argtypes, fn.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise c.WinError(c.get_last_error())
        limits = Extended()
        limits.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, c.byref(limits), c.sizeof(limits)):
            error = c.WinError(c.get_last_error())
            self.close()
            raise error

    def assign(self, proc):
        if not self.api.AssignProcessToJobObject(self.handle, int(proc._handle)):
            raise self.c.WinError(self.c.get_last_error())

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def spawn(command, env):
    job = WindowsJob() if sys.platform == 'win32' else None
    options = {'creationflags': 0x08000000 | 0x00000200} if job else {'start_new_session': True}
    proc = None
    try:
        with external_dll_search():
            proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, env=child_environment(env), **options)
        if job:
            job.assign(proc)
        return proc, job
    except BaseException:
        if proc is not None:
            proc.kill()
            proc.wait()
            proc.stdout.close()
            proc.stderr.close()
        if job:
            job.close()
        raise


class ThreadedPipes:
    """Windows cannot select anonymous pipes. Reader threads feed a bounded queue."""
    def __init__(self, pipes):
        self.queue = queue.Queue(maxsize=64)
        self.stop = threading.Event()
        self.threads = []
        self.remaining = len(pipes)
        for pipe in pipes:
            thread = threading.Thread(target=self._read, args=(pipe,), daemon=True, name='mkv-tool-pipe')
            thread.start()
            self.threads.append(thread)

    def _put(self, value):
        while not self.stop.is_set():
            try:
                self.queue.put(value, timeout=.1)
                return
            except queue.Full:
                pass

    def _read(self, pipe):
        try:
            while not self.stop.is_set():
                block = os.read(pipe.fileno(), 65536)
                self._put((pipe, block))
                if not block:
                    return
        except OSError as error:
            self._put((pipe, error))

    def blocks(self, check):
        while self.remaining:
            check()
            try:
                pipe, block = self.queue.get(timeout=.15)
            except queue.Empty:
                continue
            if isinstance(block, OSError):
                raise block
            if not block:
                self.remaining -= 1
            yield pipe, block

    def close(self):
        self.stop.set()
        for thread in self.threads:
            thread.join(timeout=2)
