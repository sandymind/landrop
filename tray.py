"""
Tray icon Windows (system tray / notification area) memakai ctypes murni.
Menyediakan: icon + tooltip, klik kiri, menu klik kanan, dan notifikasi balon.
"""
import ctypes
import threading
from ctypes import wintypes as W

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_NULL = 0x0000
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_APP = 0x8000
WM_TRAY = WM_APP + 1
WM_RUN = WM_APP + 2  # jalankan fungsi di thread tray
NIN_BALLOONUSERCLICK = 0x0405

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10
NIIF_USER, NIIF_LARGE_ICON = 0x4, 0x20

MF_STRING, MF_SEPARATOR, MF_CHECKED, MF_GRAYED = 0x0, 0x800, 0x8, 0x1
TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_NONOTIFY = 0x2, 0x100, 0x80
IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x10, 0x40
IDI_APPLICATION = 32512


class GUID(ctypes.Structure):
    _fields_ = [("Data1", W.DWORD), ("Data2", W.WORD), ("Data3", W.WORD), ("Data4", W.BYTE * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("hWnd", W.HWND), ("uID", W.UINT), ("uFlags", W.UINT),
                ("uCallbackMessage", W.UINT), ("hIcon", W.HICON), ("szTip", W.WCHAR * 128),
                ("dwState", W.DWORD), ("dwStateMask", W.DWORD), ("szInfo", W.WCHAR * 256),
                ("uVersion", W.UINT), ("szInfoTitle", W.WCHAR * 64), ("dwInfoFlags", W.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", W.HICON)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", W.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", W.HINSTANCE), ("hIcon", W.HICON),
                ("hCursor", W.HANDLE), ("hbrBackground", W.HBRUSH), ("lpszMenuName", W.LPCWSTR),
                ("lpszClassName", W.LPCWSTR)]


class POINT(ctypes.Structure):
    _fields_ = [("x", W.LONG), ("y", W.LONG)]


user32.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID]
user32.CreateWindowExW.restype = W.HWND
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = W.ATOM
user32.RegisterWindowMessageW.argtypes = [W.LPCWSTR]
user32.RegisterWindowMessageW.restype = W.UINT
user32.LoadImageW.argtypes = [W.HINSTANCE, W.LPCWSTR, W.UINT, ctypes.c_int, ctypes.c_int, W.UINT]
user32.LoadImageW.restype = W.HANDLE
user32.LoadIconW.argtypes = [W.HINSTANCE, W.LPVOID]
user32.LoadIconW.restype = W.HICON
user32.CreatePopupMenu.restype = W.HMENU
user32.AppendMenuW.argtypes = [W.HMENU, W.UINT, ctypes.c_size_t, W.LPCWSTR]
user32.SetMenuDefaultItem.argtypes = [W.HMENU, W.UINT, W.UINT]
user32.TrackPopupMenu.argtypes = [W.HMENU, W.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.HWND, W.LPVOID]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.DestroyMenu.argtypes = [W.HMENU]
user32.SetForegroundWindow.argtypes = [W.HWND]
user32.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.GetMessageW.argtypes = [ctypes.POINTER(W.MSG), W.HWND, W.UINT, W.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(W.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(W.MSG)]
user32.DestroyWindow.argtypes = [W.HWND]
shell32.Shell_NotifyIconW.argtypes = [W.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = W.BOOL
kernel32.GetModuleHandleW.argtypes = [W.LPCWSTR]
kernel32.GetModuleHandleW.restype = W.HMODULE


class Tray:
    """
    menu: fungsi yang mengembalikan list item: (label, callback, checked) atau None untuk pemisah.
    Item pertama menjadi item default (tebal) dan juga dijalankan saat klik kiri.
    """

    def __init__(self, icon_path, tooltip, menu, on_balloon_click=None):
        self.icon_path = icon_path
        self.tooltip = tooltip
        self.menu = menu
        self.on_balloon_click = on_balloon_click
        self.hwnd = None
        self.hicon = None
        self.ok = False
        self._ready = threading.Event()
        self._calls = []
        self._lock = threading.Lock()
        self._wndproc = WNDPROC(self._proc)  # simpan referensi agar tidak di-GC

    # ---- API (aman dipanggil dari thread mana pun)
    def start(self):
        threading.Thread(target=self._run, name="tray", daemon=True).start()
        self._ready.wait(5)
        return self.ok

    def set_tooltip(self, text):
        self.tooltip = text
        self._call(lambda: self._notify(NIM_MODIFY, NIF_TIP))

    def balloon(self, title, text):
        def f():
            nid = self._nid(NIF_INFO)
            nid.szInfoTitle = title[:63]
            nid.szInfo = (text or " ")[:255]
            nid.dwInfoFlags = NIIF_USER | NIIF_LARGE_ICON
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        self._call(f)

    def remove(self):
        """Hapus icon (dipanggil sebelum proses keluar)."""
        if self.hwnd:
            self._notify(NIM_DELETE, 0)
            self.ok = False

    # ---- internal
    def _call(self, fn):
        if not self.hwnd:
            return
        with self._lock:
            self._calls.append(fn)
        user32.PostMessageW(self.hwnd, WM_RUN, 0, 0)

    def _nid(self, flags):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = flags
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self.hicon
        nid.szTip = self.tooltip[:127]
        return nid

    def _notify(self, op, flags):
        return bool(shell32.Shell_NotifyIconW(op, ctypes.byref(self._nid(flags))))

    def _add(self):
        return self._notify(NIM_ADD, NIF_MESSAGE | NIF_ICON | NIF_TIP)

    def _run(self):
        try:
            hinst = kernel32.GetModuleHandleW(None)
            wc = WNDCLASSW()
            wc.lpfnWndProc = self._wndproc
            wc.hInstance = hinst
            wc.lpszClassName = "LanDropTrayWindow"
            user32.RegisterClassW(ctypes.byref(wc))
            self.taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
            self.hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "LanDrop", 0, 0, 0, 0, 0,
                                               None, None, hinst, None)
            self.hicon = user32.LoadImageW(None, self.icon_path, IMAGE_ICON, 0, 0,
                                           LR_LOADFROMFILE | LR_DEFAULTSIZE) if self.icon_path else None
            if not self.hicon:
                self.hicon = user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
            self.ok = self._add()
        finally:
            self._ready.set()
        msg = W.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _show_menu(self):
        items = self.menu()
        hmenu = user32.CreatePopupMenu()
        actions = {}
        for i, it in enumerate(items):
            if it is None:
                user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
                continue
            label, cb, checked = (list(it) + [False])[:3]
            cmd = 100 + i
            actions[cmd] = cb
            flags = MF_STRING | (MF_CHECKED if checked else 0) | (MF_GRAYED if cb is None else 0)
            user32.AppendMenuW(hmenu, flags, cmd, label)
        user32.SetMenuDefaultItem(hmenu, 100, 0)
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(hmenu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY,
                                    pt.x, pt.y, 0, self.hwnd, None)
        user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(hmenu)
        if cmd in actions and actions[cmd]:
            self._safe(actions[cmd])

    def _default_action(self):
        items = self.menu()
        if items and items[0] and items[0][1]:
            self._safe(items[0][1])

    @staticmethod
    def _safe(fn):
        threading.Thread(target=fn, daemon=True).start()

    def _proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAY:
                ev = lparam & 0xFFFF
                if ev == WM_LBUTTONUP:
                    self._default_action()
                elif ev in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self._show_menu()
                elif ev == NIN_BALLOONUSERCLICK and self.on_balloon_click:
                    self._safe(self.on_balloon_click)
                return 0
            if msg == WM_RUN:
                with self._lock:
                    calls, self._calls = self._calls, []
                for fn in calls:
                    fn()
                return 0
            if msg == getattr(self, "taskbar_created", -1):  # Explorer restart: pasang ulang icon
                self.ok = self._add()
                return 0
        except Exception:
            pass
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
