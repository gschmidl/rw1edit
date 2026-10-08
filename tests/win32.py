"""ctypes helpers for driving the original RW1_EDIT.EXE (Windows only)"""
import ctypes
import os
import subprocess
import time
from ctypes import wintypes as wt

user32 = ctypes.WinDLL('user32', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

LRESULT = ctypes.c_ssize_t
WPARAM, LPARAM = ctypes.c_size_t, ctypes.c_ssize_t
user32.SendMessageA.argtypes = [wt.HWND, wt.UINT, WPARAM, LPARAM]
user32.SendMessageA.restype = LRESULT
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, WPARAM, LPARAM]
user32.SendMessageW.restype = LRESULT
user32.SendMessageTimeoutA.argtypes = [wt.HWND, wt.UINT, WPARAM, LPARAM, wt.UINT, wt.UINT,
                                       ctypes.POINTER(ctypes.c_size_t)]
user32.SendMessageTimeoutA.restype = LRESULT
user32.PostMessageA.argtypes = [wt.HWND, wt.UINT, WPARAM, LPARAM]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                wt.UINT]
user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetDlgItem.argtypes = [wt.HWND, ctypes.c_int]
user32.GetDlgItem.restype = wt.HWND
user32.FindWindowExW.argtypes = [wt.HWND, wt.HWND, wt.LPCWSTR, wt.LPCWSTR]
user32.FindWindowExW.restype = wt.HWND
user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.GetWindow.argtypes = [wt.HWND, wt.UINT]
user32.GetWindow.restype = wt.HWND
user32.GetDlgCtrlID.argtypes = [wt.HWND]
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, LPARAM]
user32.EnumChildWindows.argtypes = [wt.HWND, WNDENUMPROC, LPARAM]
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.ReadProcessMemory.argtypes = [wt.HANDLE, wt.LPCVOID, wt.LPVOID, ctypes.c_size_t,
                                       ctypes.POINTER(ctypes.c_size_t)]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.VirtualAllocEx.argtypes = [wt.HANDLE, wt.LPVOID, ctypes.c_size_t, wt.DWORD, wt.DWORD]
kernel32.VirtualAllocEx.restype = ctypes.c_size_t
kernel32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t,
                                        ctypes.POINTER(ctypes.c_size_t)]
kernel32.CreateRemoteThread.argtypes = [wt.HANDLE, wt.LPVOID, ctypes.c_size_t, ctypes.c_size_t, wt.LPVOID,
                                        wt.DWORD, wt.LPVOID]
kernel32.CreateRemoteThread.restype = wt.HANDLE
kernel32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
kernel32.GetExitCodeThread.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wt.HGLOBAL
kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
kernel32.GlobalLock.restype = wt.LPVOID
kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
kernel32.GlobalSize.argtypes = [wt.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t
user32.OpenClipboard.argtypes = [wt.HWND]
user32.GetClipboardData.argtypes = [wt.UINT]
user32.GetClipboardData.restype = wt.HANDLE
user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
user32.SetClipboardData.restype = wt.HANDLE
user32.IsClipboardFormatAvailable.argtypes = [wt.UINT]

WM_SIZE, WM_ACTIVATE, WM_CLOSE, WM_KEYDOWN, WM_KEYUP, WM_CHAR = 0x05, 0x06, 0x10, 0x100, 0x101, 0x102
WM_COMMAND, WM_TIMER, WM_VSCROLL, WM_SETTEXT, WM_GETTEXT = 0x111, 0x113, 0x115, 0x0C, 0x0D
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_RBUTTONDOWN = 0x200, 0x201, 0x202, 0x204
BM_CLICK = 0xF5
CF_TEXT, CF_UNICODETEXT = 1, 13


def class_name(hwnd):
    b = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, b, 256)
    return b.value


def window_text(hwnd):
    b = ctypes.create_unicode_buffer(1024)
    user32.GetWindowTextW(hwnd, b, 1024)
    return b.value


def windows_of(pid):
    out = []

    def cb(h, _):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid:
            out.append(h)
        return True
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def children(hwnd):
    out = []

    def cb(h, _):
        out.append(h)
        return True
    user32.EnumChildWindows(hwnd, WNDENUMPROC(cb), 0)
    return out


class Original:
    """RW1_EDIT.EXE started from a scratch folder, driven by window messages"""

    def __init__(self, exe, cwd, x=-2400, y=80, w=320, h=500):
        # inherited by the child: no "has stopped working" box when it crashes
        kernel32.SetErrorMode(0x8003)
        si = subprocess.STARTUPINFO()
        si.dwFlags = subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 4          # SW_SHOWNOACTIVATE
        self.proc = subprocess.Popen([exe], cwd=cwd, startupinfo=si)
        self.hwnd = None
        for _ in range(200):
            for hw in windows_of(self.proc.pid):
                if class_name(hw) == 'Editors':
                    self.hwnd = hw
            if self.hwnd:
                break
            time.sleep(0.05)
        if not self.hwnd:
            self.kill()
            raise RuntimeError('no editor window')
        # VM_OPERATION | VM_READ | QUERY_INFORMATION
        self.hproc = kernel32.OpenProcess(0x0418, False, self.proc.pid)
        for _ in range(100):
            if user32.IsWindowVisible(self.hwnd):
                break
            time.sleep(0.02)
        time.sleep(0.1)
        self.status_hwnd = None
        for c in children(self.hwnd):
            if class_name(c) == 'msctls_statusbar32':
                self.status_hwnd = c
        self.remote = kernel32.VirtualAllocEx(self.hproc, None, 4096, 0x3000, 0x04)
        self.place(x, y, w, h)
        time.sleep(0.5)     # the timer ticks the drag counter up to 2

    def place(self, x, y, w, h):
        """move and size the window until it stays so (moving a DPI-unaware window
        to a monitor with another scale makes Windows resize it once more)"""
        good = 0
        for _ in range(20):
            r = wt.RECT()
            user32.GetWindowRect(self.hwnd, ctypes.byref(r))
            if (r.left, r.top, r.right - r.left, r.bottom - r.top) == (x, y, w, h):
                good += 1
                if good == 2:
                    return
            else:
                good = 0
                self.move(x, y, w, h)
            time.sleep(0.15)
        raise RuntimeError('the window does not stay at %d,%d %dx%d' % (x, y, w, h))

    def move(self, x, y, w, h):
        user32.SetWindowPos(self.hwnd, None, x, y, w, h, 0x0014)     # NOZORDER | NOACTIVATE

    def client(self):
        r = wt.RECT()
        user32.GetClientRect(self.hwnd, ctypes.byref(r))
        return r.right - r.left, r.bottom - r.top

    def alive(self):
        return self.proc.poll() is None

    def kill(self):
        if self.proc.poll() is None:
            self.proc.kill()
            self.proc.wait()
        if getattr(self, 'hproc', None):
            kernel32.CloseHandle(self.hproc)
            self.hproc = None

    def read(self, addr, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not kernel32.ReadProcessMemory(self.hproc, addr, buf, n, ctypes.byref(got)):
            raise OSError('ReadProcessMemory %08X failed (%d)' % (addr, ctypes.get_last_error()))
        return buf.raw

    def u32(self, addr):
        return int.from_bytes(self.read(addr, 4), 'little')

    def i32(self, addr):
        return int.from_bytes(self.read(addr, 4), 'little', signed=True)

    def send(self, msg, wparam=0, lparam=0, timeout=3000):
        res = ctypes.c_size_t()
        ok = user32.SendMessageTimeoutA(self.hwnd, msg, wparam, lparam, 0x0002, timeout, ctypes.byref(res))
        if not ok:
            raise TimeoutError('message %04X %X not answered (hung?)' % (msg, wparam))
        return res.value

    def post(self, msg, wparam=0, lparam=0):
        user32.PostMessageA(self.hwnd, msg, wparam, lparam)

    def title(self):
        return window_text(self.hwnd)

    def status_text(self):
        """part 0 of the status bar (SB_GETTEXTA into a buffer in the editor's process)"""
        res = ctypes.c_size_t()
        user32.SendMessageTimeoutA(self.status_hwnd, 0x0402, 0, self.remote, 0x0002, 3000, ctypes.byref(res))
        return self.read(self.remote, 256).split(b'\0')[0].decode('latin-1')

    def dialog(self, timeout=5.0):
        """the modal dialog the editor has opened"""
        end = time.time() + timeout
        while time.time() < end:
            for h in windows_of(self.proc.pid):
                if class_name(h) == '#32770' and user32.IsWindowVisible(h):
                    return h
            time.sleep(0.05)
        return None

    def wait_no_dialog(self, timeout=5.0):
        end = time.time() + timeout
        while time.time() < end:
            if not any(class_name(h) == '#32770' and user32.IsWindowVisible(h)
                       for h in windows_of(self.proc.pid)):
                return True
            time.sleep(0.05)
        return False

    def call_this(self, func, this, arg, timeout=10.0):
        """run the original's __thiscall func(this, arg) in a thread of its own
        (while its window thread waits for messages); arg: bytes -> pointer to them"""
        h = kernel32.OpenProcess(0x043A, False, self.proc.pid)  # CREATE_THREAD|VM_OPERATION|VM_READ|VM_WRITE|QUERY
        try:
            mem = kernel32.VirtualAllocEx(h, None, 4096, 0x3000, 0x40)
            data = arg + b'\0'
            stub = (b'\xB9' + this.to_bytes(4, 'little') +             # mov ecx, this
                    b'\x68' + (mem + 64).to_bytes(4, 'little') +       # push arg
                    b'\xB8' + func.to_bytes(4, 'little') +             # mov eax, func
                    b'\xFF\xD0' +                                      # call eax
                    b'\xC2\x04\x00')                                   # ret 4
            blob = stub.ljust(64, b'\x90') + data
            n = ctypes.c_size_t()
            kernel32.WriteProcessMemory(h, mem, blob, len(blob), ctypes.byref(n))
            th = kernel32.CreateRemoteThread(h, None, 0, mem, None, 0, None)
            if not th:
                raise OSError('CreateRemoteThread failed (%d)' % ctypes.get_last_error())
            kernel32.WaitForSingleObject(th, int(timeout * 1000))
            code = wt.DWORD()
            kernel32.GetExitCodeThread(th, ctypes.byref(code))
            kernel32.CloseHandle(th)
            return code.value
        finally:
            kernel32.CloseHandle(h)

    def file_dialog(self, cmd, path):
        """File > Open (101) or Save as (103): type the path and press OK"""
        self.post(WM_COMMAND, cmd, 0)
        dlg = self.dialog()
        if not dlg:
            raise RuntimeError('no file dialog')
        time.sleep(0.3)
        edit = None
        combo = user32.GetDlgItem(dlg, 0x47C)
        if combo:
            edit = user32.FindWindowExW(combo, None, 'Edit', None)
            if not edit:
                inner = user32.FindWindowExW(combo, None, 'ComboBox', None)
                if inner:
                    edit = user32.FindWindowExW(inner, None, 'Edit', None)
        if not edit:
            edit = user32.GetDlgItem(dlg, 0x480)
        if not edit:
            raise RuntimeError('no file name field')
        b = ctypes.create_unicode_buffer(path)
        user32.SendMessageW(edit, WM_SETTEXT, 0, ctypes.cast(b, ctypes.c_void_p).value)
        ok = user32.GetDlgItem(dlg, 1)
        user32.PostMessageA(ok, BM_CLICK, 0, 0)
        return self.wait_no_dialog()

    def answer_box(self, button_id, timeout=3.0):
        """press a button (6 Yes, 7 No, 2 Cancel, 1 OK) in a message box; its text"""
        dlg = self.dialog(timeout)
        if not dlg:
            return None
        text = ''
        for c in children(dlg):
            if class_name(c) == 'Static' and window_text(c):
                text += window_text(c)
        btn = user32.GetDlgItem(dlg, button_id)
        user32.PostMessageA(btn, BM_CLICK, 0, 0)
        self.wait_no_dialog()
        return text


# -- the clipboard -----------------------------------------------------------

def _open_clipboard():
    for _ in range(100):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def clipboard_get_text():
    """CF_TEXT bytes, or None"""
    if not _open_clipboard():
        raise RuntimeError('clipboard busy')
    try:
        if not user32.IsClipboardFormatAvailable(CF_TEXT):
            return None
        h = user32.GetClipboardData(CF_TEXT)
        p = kernel32.GlobalLock(h)
        try:
            return ctypes.string_at(p)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def clipboard_get_unicode():
    if not _open_clipboard():
        raise RuntimeError('clipboard busy')
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        h = user32.GetClipboardData(CF_UNICODETEXT)
        p = kernel32.GlobalLock(h)
        try:
            return ctypes.wstring_at(p)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def clipboard_set_bytes(data):
    """CF_TEXT (Windows makes the Unicode form from it)"""
    if not _open_clipboard():
        raise RuntimeError('clipboard busy')
    try:
        user32.EmptyClipboard()
        h = kernel32.GlobalAlloc(0x2042, len(data) + 1)
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, data + b'\0', len(data) + 1)
        kernel32.GlobalUnlock(h)
        user32.SetClipboardData(CF_TEXT, h)
    finally:
        user32.CloseClipboard()


def clipboard_set_unicode(text):
    if not _open_clipboard():
        raise RuntimeError('clipboard busy')
    try:
        user32.EmptyClipboard()
        if text is not None:
            data = text.encode('utf-16-le') + b'\0\0'
            h = kernel32.GlobalAlloc(0x2042, len(data))
            p = kernel32.GlobalLock(h)
            ctypes.memmove(p, data, len(data))
            kernel32.GlobalUnlock(h)
            user32.SetClipboardData(CF_UNICODETEXT, h)
    finally:
        user32.CloseClipboard()


def scratch_copy(exe, folder):
    os.makedirs(folder, exist_ok=True)
    dst = os.path.join(folder, 'RW1_EDIT.EXE')
    with open(exe, 'rb') as f, open(dst, 'wb') as g:
        g.write(f.read())
    return dst
