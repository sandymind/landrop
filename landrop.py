"""
LanDrop - chat & kirim file antar laptop Windows di jaringan yang sama.
Hanya memakai Python standard library. Di-build jadi LanDrop.exe dengan PyInstaller.
"""
import ctypes
import hashlib
import http.client
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP = "LanDrop"
VERSION = "1.1.0"
HTTP_PORT = int(os.environ.get("LANDROP_PORT", "47801"))
UDP_PORT = int(os.environ.get("LANDROP_UDP", "47800"))
DATA_DIR = os.environ.get("LANDROP_DATA") or os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), APP)
INSTALL_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Programs", APP)
INSTALLED_EXE = os.path.join(INSTALL_DIR, APP + ".exe")
FROZEN = getattr(sys, "frozen", False)
CHUNK = 256 * 1024
PEER_TIMEOUT = 12
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\LanDrop"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def now_ms():
    return int(time.time() * 1000)


def msgbox(text, title=APP, flags=0x40):
    try:
        return ctypes.windll.user32.MessageBoxW(0, text, title, flags | 0x10000)
    except Exception:
        print(text)
        return 6


def safe_name(name):
    name = os.path.basename(name.replace("\\", "/")) or "file"
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name[:180] or "file"


def unique_path(folder, name):
    base, ext = os.path.splitext(name)
    path = os.path.join(folder, name)
    i = 1
    while os.path.exists(path) or os.path.exists(path + ".part"):
        path = os.path.join(folder, f"{base} ({i}){ext}")
        i += 1
    return path


def local_ips():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    try:  # alamat dari rute default
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return sorted(ip for ip in ips if not ip.startswith("127.") and not ip.startswith("169.254."))


# ---------------------------------------------------------------- state
class State:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.lock = threading.RLock()
        self.cfg_path = os.path.join(DATA_DIR, "config.json")
        self.hist_path = os.path.join(DATA_DIR, "history.json")
        self.cfg = self._load(self.cfg_path, {})
        self.cfg.setdefault("id", uuid.uuid4().hex)
        self.cfg.setdefault("name", socket.gethostname())
        self.cfg.setdefault("key", "")
        self.cfg.setdefault("save_dir", os.path.join(os.path.expanduser("~"), "Downloads", APP))
        self.cfg.setdefault("open_on_receive", True)
        self.cfg.setdefault("manual", [])
        self.cfg.setdefault("known", {})
        self.history = self._load(self.hist_path, [])
        for m in self.history:  # transfer yang terputus saat app ditutup
            if m.get("status") in ("sending", "receiving"):
                m["status"] = "failed"
        self.peers = {}
        self.subs = []
        self._dirty = False
        self.save_cfg()
        threading.Thread(target=self._saver, daemon=True).start()

    @staticmethod
    def _load(path, default):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    @staticmethod
    def _dump(path, data):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)

    def save_cfg(self):
        with self.lock:
            self._dump(self.cfg_path, self.cfg)

    def _saver(self):
        while True:
            time.sleep(1)
            if self._dirty:
                with self.lock:
                    self._dirty = False
                    data = list(self.history[-5000:])
                try:
                    self._dump(self.hist_path, data)
                except Exception:
                    pass

    # auth: hash dari "kunci pasangan" yang sama di semua laptop
    def key_tag(self):
        return hashlib.sha256(("tag:" + self.cfg["key"]).encode()).hexdigest()[:12]

    def auth(self):
        return hashlib.sha256(("auth:" + self.cfg["key"]).encode()).hexdigest()

    def emit(self, event, data):
        for q in list(self.subs):
            q.put((event, data))
        if event in ("peers", "settings"):
            update_tray_tip()

    def me(self):
        return {"id": self.cfg["id"], "name": self.cfg["name"], "port": HTTP_PORT,
                "ips": local_ips(), "version": VERSION, "tray": bool(TRAY and TRAY.ok)}

    def public_peers(self):
        with self.lock:
            return [dict(p) for p in self.peers.values()]

    def settings(self):
        c = self.cfg
        return {"name": c["name"], "key": c["key"], "save_dir": c["save_dir"],
                "open_on_receive": c["open_on_receive"], "manual": c["manual"],
                "autostart": get_autostart(), "installed": is_installed_copy(),
                "frozen": FROZEN}

    def touch_peer(self, pid, name, ip, port, manual=False):
        with self.lock:
            p = self.peers.get(pid)
            changed = p is None or p["name"] != name or p["ip"] != ip or p["port"] != port
            self.peers[pid] = {"id": pid, "name": name, "ip": ip, "port": port,
                               "seen": time.time(), "manual": manual or (p or {}).get("manual", False)}
            if self.cfg["known"].get(pid) != name:
                self.cfg["known"][pid] = name
                self.save_cfg()
        if changed:
            self.emit("peers", {"peers": self.public_peers(), "known": self.cfg["known"]})
        return changed

    def expire_peers(self):
        cut = time.time() - PEER_TIMEOUT
        with self.lock:
            gone = [k for k, p in self.peers.items() if p["seen"] < cut]
            for k in gone:
                del self.peers[k]
        if gone:
            self.emit("peers", {"peers": self.public_peers(), "known": self.cfg["known"]})

    def add_msg(self, m):
        with self.lock:
            self.history.append(m)
            self._dirty = True
        self.emit("msg", m)
        return m

    def update_msg(self, m, **kw):
        with self.lock:
            m.update(kw)
            self._dirty = True
        self.emit("msg", m)

    def find_msg(self, mid):
        with self.lock:
            for m in reversed(self.history):
                if m["id"] == mid:
                    return m
        return None


S = None  # State
TRAY = None  # tray.Tray
_last_auto_open = 0


def maybe_open_window():
    global _last_auto_open
    if S.cfg.get("open_on_receive") and not S.subs and time.time() - _last_auto_open > 15:
        _last_auto_open = time.time()
        open_window()


# ---------------------------------------------------------------- tray icon
def update_tray_tip():
    if TRAY and S:
        n = len(S.peers)
        TRAY.set_tooltip(f"LanDrop – {S.cfg['name']}\n" +
                         (f"{n} perangkat online" if n else "Belum ada perangkat online"))


def notify_incoming(pid, text):
    """Notifikasi balon jika jendela LanDrop sedang tidak terbuka."""
    if TRAY and not S.subs:
        TRAY.balloon(S.cfg["known"].get(pid) or "LanDrop", text)


def open_save_dir():
    os.makedirs(S.cfg["save_dir"], exist_ok=True)
    reveal(S.cfg["save_dir"])


def quit_app():
    if TRAY:
        TRAY.remove()
    os._exit(0)


def tray_menu():
    auto = get_autostart()
    n = len(S.peers)
    return [
        ("Buka LanDrop", open_window),
        ("Buka folder file diterima", open_save_dir),
        None,
        (f"{n} perangkat online" if n else "Belum ada perangkat online", None),
        ("Jalankan saat Windows menyala", lambda: (set_autostart(not auto),
                                                    S.emit("settings", {"settings": S.settings(), "me": S.me()})), auto),
        None,
        ("Keluar", quit_app),
    ]


def start_tray():
    global TRAY
    if os.environ.get("LANDROP_NOTRAY"):
        return
    try:
        import tray
        TRAY = tray.Tray(resource("icon.ico"), "LanDrop", tray_menu, on_balloon_click=open_window)
        if not TRAY.start():
            TRAY = None
        update_tray_tip()
    except Exception:
        TRAY = None


# ---------------------------------------------------------------- discovery
def broadcast_targets():
    t = {"255.255.255.255"}
    for ip in local_ips():
        t.add(".".join(ip.split(".")[:3] + ["255"]))
    return t


def discovery_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", UDP_PORT))
    sock.settimeout(1.0)

    def packet(reply=False):
        return json.dumps({"app": "landrop", "v": 1, "id": S.cfg["id"], "name": S.cfg["name"],
                           "port": HTTP_PORT, "kt": S.key_tag(), "reply": reply}).encode()

    last = 0
    while True:
        if time.time() - last > 3:
            last = time.time()
            for t in broadcast_targets():
                try:
                    sock.sendto(packet(), (t, UDP_PORT))
                except OSError:
                    pass
            S.expire_peers()
        try:
            data, addr = sock.recvfrom(4096)
        except (socket.timeout, ConnectionResetError, OSError):
            continue
        try:
            d = json.loads(data.decode())
        except Exception:
            continue
        if d.get("app") != "landrop" or d.get("id") == S.cfg["id"] or d.get("kt") != S.key_tag():
            continue
        is_new = S.touch_peer(d["id"], str(d.get("name", "?"))[:60], addr[0], int(d.get("port", HTTP_PORT)))
        if is_new and not d.get("reply"):
            try:
                sock.sendto(packet(reply=True), addr)
            except OSError:
                pass


def manual_loop():
    while True:
        for addr in list(S.cfg.get("manual", [])):
            host, _, port = addr.partition(":")
            try:
                info = peer_request(host, int(port or HTTP_PORT), "GET", "/peer/hello", timeout=3)
                if info.get("id") and info["id"] != S.cfg["id"]:
                    S.touch_peer(info["id"], info.get("name", host), host, int(port or HTTP_PORT), manual=True)
            except Exception:
                pass
        time.sleep(5)


def peer_request(ip, port, method, path, body=None, timeout=15):
    conn = http.client.HTTPConnection(ip, port, timeout=timeout)
    headers = {"X-LanDrop-Auth": S.auth(), "X-From": S.cfg["id"],
               "X-From-Name": urllib.parse.quote(S.cfg["name"])}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=data, headers=headers)
    r = conn.getresponse()
    raw = r.read()
    conn.close()
    if r.status != 200:
        raise IOError(f"HTTP {r.status}: {raw[:200]!r}")
    return json.loads(raw or b"{}")


# ---------------------------------------------------------------- windows helpers
def find_edge():
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.environ.get("LOCALAPPDATA")):
        if base:
            p = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.exists(p):
                return p
    return None


def open_window():
    url = f"http://localhost:{HTTP_PORT}/"
    edge = find_edge()
    try:
        if edge:
            subprocess.Popen([edge, f"--app={url}", "--window-size=1040,740"], creationflags=NO_WINDOW)
            return
    except Exception:
        pass
    webbrowser.open(url)


def launch_command(extra=""):
    if FROZEN:
        cmd = f'"{sys.executable}"'
    else:
        pyw = sys.executable.replace("python.exe", "pythonw.exe")
        cmd = f'"{pyw}" "{os.path.abspath(__file__)}"'
    return (cmd + " " + extra).strip()


def get_autostart():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP)
            return True
    except Exception:
        return False


def set_autostart(on):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, launch_command("--background"))
        else:
            try:
                winreg.DeleteValue(k, APP)
            except FileNotFoundError:
                pass


def is_installed_copy():
    return FROZEN and os.path.normcase(os.path.abspath(sys.executable)) == os.path.normcase(INSTALLED_EXE)


def reveal(path):
    if os.path.isdir(path):
        os.startfile(path)
    else:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "LanDrop/" + VERSION

    def log_message(self, *a):
        pass

    # --- helpers
    def send_json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def fail(self, code, text):
        self.close_connection = True
        self.send_json({"error": text}, code)

    def read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def is_local_ui(self):
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            return False
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("localhost", "127.0.0.1"):
            return False  # cegah DNS rebinding
        origin = self.headers.get("Origin")
        if origin and urllib.parse.urlparse(origin).hostname not in ("localhost", "127.0.0.1"):
            return False  # cegah website lain memanggil API lokal
        return True

    def peer_ok(self):
        return self.headers.get("X-LanDrop-Auth") == S.auth()

    def route(self):
        u = urllib.parse.urlparse(self.path)
        return u.path, dict(urllib.parse.parse_qsl(u.query))

    # --- GET
    def do_GET(self):
        path, q = self.route()
        if path.startswith("/peer/"):
            if not self.peer_ok():
                return self.fail(403, "kunci pasangan tidak cocok")
            if path == "/peer/hello":
                return self.send_json({"id": S.cfg["id"], "name": S.cfg["name"], "version": VERSION})
            return self.fail(404, "not found")
        if not self.is_local_ui():
            return self.fail(403, "forbidden")
        if path in ("/", "/index.html"):
            with open(resource("ui.html"), "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        elif path == "/icon.ico":
            p = resource("icon.ico")
            if not os.path.exists(p):
                return self.fail(404, "no icon")
            self.serve_file(p, "image/x-icon")
        elif path == "/api/ping":
            self.send_json({"app": APP, "id": S.cfg["id"]})
        elif path == "/api/state":
            with S.lock:
                hist = list(S.history[-3000:])
            self.send_json({"me": S.me(), "peers": S.public_peers(), "known": S.cfg["known"],
                            "history": hist, "settings": S.settings()})
        elif path == "/api/events":
            self.sse()
        elif path.startswith("/api/file/"):
            m = S.find_msg(path.rsplit("/", 1)[-1])
            if not m or not m.get("path") or not os.path.exists(m["path"]):
                return self.fail(404, "file tidak ada")
            self.serve_file(m["path"], m.get("mime") or "application/octet-stream")
        else:
            self.fail(404, "not found")

    def serve_file(self, p, mime):
        size = os.path.getsize(p)
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "max-age=3600")
        self.end_headers()
        with open(p, "rb") as f:
            shutil.copyfileobj(f, self.wfile, CHUNK)

    def sse(self):
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        q = queue.Queue()
        S.subs.append(q)
        try:
            self.wfile.write(b"retry: 1500\n\n")
            self.wfile.flush()
            while True:
                try:
                    ev, data = q.get(timeout=15)
                    self.wfile.write(f"event: {ev}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except Exception:
            pass
        finally:
            if q in S.subs:
                S.subs.remove(q)

    # --- POST
    def do_POST(self):
        path, q = self.route()
        if path.startswith("/peer/"):
            if not self.peer_ok():
                return self.fail(403, "kunci pasangan tidak cocok")
            if path == "/peer/text":
                return self.peer_text()
            if path == "/peer/file":
                return self.peer_file()
            return self.fail(404, "not found")
        if not self.is_local_ui():
            return self.fail(403, "forbidden")
        try:
            if path == "/api/send-text":
                return self.api_send_text()
            if path == "/api/send-file":
                return self.api_send_file(q)
            if path == "/api/settings":
                return self.api_settings()
            if path == "/api/open":
                b = self.read_json()
                m = S.find_msg(b.get("id", ""))
                if b.get("what") == "savedir":
                    open_save_dir()
                elif m and m.get("path") and os.path.exists(m["path"]):
                    if b.get("what") == "folder":
                        reveal(m["path"])
                    else:
                        os.startfile(m["path"])
                else:
                    return self.fail(404, "file tidak ditemukan")
                return self.send_json({"ok": True})
            if path == "/api/clear":
                pid = self.read_json().get("peer")
                with S.lock:
                    S.history[:] = [m for m in S.history if m["peer"] != pid]
                    S._dirty = True
                S.emit("cleared", {"peer": pid})
                return self.send_json({"ok": True})
            if path == "/api/quit":
                self.send_json({"ok": True})
                threading.Thread(target=lambda: (time.sleep(0.3), quit_app()), daemon=True).start()
                return
            self.fail(404, "not found")
        except Exception as e:
            self.fail(500, str(e))

    def api_settings(self):
        b = self.read_json()
        with S.lock:
            if "name" in b and b["name"].strip():
                S.cfg["name"] = b["name"].strip()[:60]
            if "key" in b:
                S.cfg["key"] = b["key"]
                S.peers.clear()
            if "save_dir" in b and b["save_dir"].strip():
                os.makedirs(b["save_dir"].strip(), exist_ok=True)
                S.cfg["save_dir"] = b["save_dir"].strip()
            if "open_on_receive" in b:
                S.cfg["open_on_receive"] = bool(b["open_on_receive"])
            if "add_manual" in b:
                a = b["add_manual"].strip()
                if a and a not in S.cfg["manual"]:
                    S.cfg["manual"].append(a)
            if "remove_manual" in b:
                S.cfg["manual"] = [a for a in S.cfg["manual"] if a != b["remove_manual"]]
            S.save_cfg()
        if "autostart" in b:
            set_autostart(bool(b["autostart"]))
        S.emit("peers", {"peers": S.public_peers(), "known": S.cfg["known"]})
        S.emit("settings", {"settings": S.settings(), "me": S.me()})
        self.send_json({"ok": True, "settings": S.settings()})

    def get_peer(self, pid):
        p = S.peers.get(pid)
        if not p:
            raise IOError("Perangkat sedang offline")
        return p

    def api_send_text(self):
        b = self.read_json()
        pid, text = b.get("peer"), b.get("text", "")
        m = S.add_msg({"id": uuid.uuid4().hex, "peer": pid, "dir": "out", "type": "text",
                       "text": text, "ts": now_ms(), "status": "sending"})

        def work():
            try:
                p = self.get_peer(pid)
                peer_request(p["ip"], p["port"], "POST", "/peer/text",
                             {"id": m["id"], "text": text, "ts": m["ts"]})
                S.update_msg(m, status="sent")
            except Exception as e:
                S.update_msg(m, status="failed", error=str(e))
        threading.Thread(target=work, daemon=True).start()
        self.send_json({"ok": True, "id": m["id"]})

    def api_send_file(self, q):
        self.close_connection = True
        pid = q.get("peer")
        name = safe_name(q.get("name", "file"))
        mime = q.get("mime") or "application/octet-stream"
        length = int(self.headers.get("Content-Length") or 0)
        m = S.add_msg({"id": uuid.uuid4().hex, "peer": pid, "dir": "out", "type": "file",
                       "name": name, "size": length, "mime": mime, "ts": now_ms(),
                       "status": "sending"})
        tee = None
        if mime.startswith("image/") and length <= 30 * 1024 * 1024:
            sent_dir = os.path.join(DATA_DIR, "sent")
            os.makedirs(sent_dir, exist_ok=True)
            tee_path = os.path.join(sent_dir, m["id"] + "_" + name)
            tee = open(tee_path, "wb")
            m["path"] = tee_path
        conn = None
        try:
            p = self.get_peer(pid)
            conn = http.client.HTTPConnection(p["ip"], p["port"], timeout=60)
            conn.putrequest("POST", "/peer/file")
            for k, v in {"Content-Length": str(length), "Content-Type": "application/octet-stream",
                         "X-LanDrop-Auth": S.auth(), "X-From": S.cfg["id"],
                         "X-From-Name": urllib.parse.quote(S.cfg["name"]),
                         "X-Name": urllib.parse.quote(name), "X-Mime": mime,
                         "X-Msg-Id": m["id"], "X-Ts": str(m["ts"])}.items():
                conn.putheader(k, v)
            conn.endheaders()
            done, last, t0 = 0, 0.0, time.time()
            while done < length:
                chunk = self.rfile.read(min(CHUNK, length - done))
                if not chunk:
                    raise IOError("upload terputus")
                conn.send(chunk)
                if tee:
                    tee.write(chunk)
                done += len(chunk)
                if time.time() - last > 0.25:
                    last = time.time()
                    S.emit("progress", {"id": m["id"], "done": done, "total": length,
                                        "speed": done / max(time.time() - t0, 0.001)})
            r = conn.getresponse()
            body = r.read()
            if r.status != 200:
                raise IOError(f"ditolak penerima: {body[:200].decode(errors='ignore')}")
            if tee:
                tee.close()
                tee = None
            S.update_msg(m, status="sent")
            self.send_json({"ok": True, "id": m["id"]})
        except Exception as e:
            S.update_msg(m, status="failed", error=str(e))
            self.send_json({"ok": False, "error": str(e)}, 502)
        finally:
            if tee:
                tee.close()
            if conn:
                conn.close()

    def sender(self):
        pid = self.headers.get("X-From", "")
        name = urllib.parse.unquote(self.headers.get("X-From-Name", "")) or "?"
        p = S.peers.get(pid)
        if p:
            S.touch_peer(pid, name, self.client_address[0], p["port"], p.get("manual", False))
        else:
            S.touch_peer(pid, name, self.client_address[0], HTTP_PORT)
        return pid

    def peer_text(self):
        b = self.read_json()
        pid = self.sender()
        S.add_msg({"id": b.get("id") or uuid.uuid4().hex, "peer": pid, "dir": "in", "type": "text",
                   "text": b.get("text", ""), "ts": now_ms(), "status": "received"})
        self.send_json({"ok": True})
        notify_incoming(pid, b.get("text", ""))
        maybe_open_window()

    def peer_file(self):
        self.close_connection = True
        pid = self.sender()
        name = safe_name(urllib.parse.unquote(self.headers.get("X-Name", "file")))
        mime = self.headers.get("X-Mime", "application/octet-stream")
        length = int(self.headers.get("Content-Length") or 0)
        folder = S.cfg["save_dir"]
        os.makedirs(folder, exist_ok=True)
        path = unique_path(folder, name)
        m = S.add_msg({"id": self.headers.get("X-Msg-Id") or uuid.uuid4().hex, "peer": pid,
                       "dir": "in", "type": "file", "name": os.path.basename(path), "size": length,
                       "mime": mime, "ts": now_ms(), "status": "receiving", "path": path})
        maybe_open_window()
        part = path + ".part"
        try:
            done, last, t0 = 0, 0.0, time.time()
            with open(part, "wb") as f:
                while done < length:
                    chunk = self.rfile.read(min(CHUNK, length - done))
                    if not chunk:
                        raise IOError("koneksi terputus")
                    f.write(chunk)
                    done += len(chunk)
                    if time.time() - last > 0.25:
                        last = time.time()
                        S.emit("progress", {"id": m["id"], "done": done, "total": length,
                                            "speed": done / max(time.time() - t0, 0.001)})
            os.replace(part, path)
            S.update_msg(m, status="received")
            notify_incoming(pid, f"📎 {m['name']} ({length / 1048576:.1f} MB) diterima")
            self.send_json({"ok": True})
        except Exception as e:
            try:
                os.remove(part)
            except OSError:
                pass
            S.update_msg(m, status="failed", error=str(e))
            self.fail(500, str(e))


# ---------------------------------------------------------------- install / uninstall
def instance_running():
    try:
        c = http.client.HTTPConnection("127.0.0.1", HTTP_PORT, timeout=1.5)
        c.request("GET", "/api/ping", headers={"Host": "localhost"})
        ok = c.getresponse().status == 200
        c.close()
        return ok
    except Exception:
        return False


def quit_running_instance():
    try:
        c = http.client.HTTPConnection("127.0.0.1", HTTP_PORT, timeout=2)
        c.request("POST", "/api/quit", body=b"{}", headers={"Host": "localhost", "Content-Length": "2"})
        c.getresponse().read()
    except Exception:
        return
    for _ in range(20):
        if not instance_running():
            break
        time.sleep(0.25)
    time.sleep(0.8)  # beri waktu exe melepas file lock


def run_ps(script):
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                   creationflags=NO_WINDOW, capture_output=True)


def ps_quote(s):
    return "'" + s.replace("'", "''") + "'"


def install():
    quit_running_instance()
    os.makedirs(INSTALL_DIR, exist_ok=True)
    for i in range(10):
        try:
            shutil.copy2(sys.executable, INSTALLED_EXE)
            break
        except PermissionError:
            time.sleep(0.5)
    else:
        msgbox("Gagal menyalin LanDrop. Tutup LanDrop yang sedang berjalan lalu coba lagi.", flags=0x10)
        return False
    exe = ps_quote(INSTALLED_EXE)
    wd = ps_quote(INSTALL_DIR)
    run_ps(
        "$w=New-Object -ComObject WScript.Shell;"
        "foreach($d in @([Environment]::GetFolderPath('Programs'),[Environment]::GetFolderPath('Desktop'))){"
        f"$s=$w.CreateShortcut((Join-Path $d 'LanDrop.lnk'));$s.TargetPath={exe};"
        f"$s.WorkingDirectory={wd};$s.IconLocation={exe}+',0';$s.Description='Chat dan kirim file antar laptop';$s.Save()}}"
    )
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
        vals = {"DisplayName": APP, "DisplayVersion": VERSION, "Publisher": APP,
                "DisplayIcon": INSTALLED_EXE, "InstallLocation": INSTALL_DIR,
                "UninstallString": f'"{INSTALLED_EXE}" --uninstall'}
        for n, v in vals.items():
            winreg.SetValueEx(k, n, 0, winreg.REG_SZ, v)
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, os.path.getsize(INSTALLED_EXE) // 1024)
    # autostart default aktif agar selalu siap menerima file
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, f'"{INSTALLED_EXE}" --background')
    subprocess.Popen([INSTALLED_EXE, "--first-run"], creationflags=NO_WINDOW)
    return True


def uninstall():
    if msgbox("Hapus LanDrop dari komputer ini?\n\nFile yang sudah diterima tidak akan dihapus.",
              flags=0x04 | 0x20) != 6:
        return
    quit_running_instance()
    import winreg
    for key, val in ((UNINSTALL_KEY, None), (RUN_KEY, APP)):
        try:
            if val:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
                    winreg.DeleteValue(k, val)
            else:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except OSError:
            pass
    run_ps("foreach($d in @([Environment]::GetFolderPath('Programs'),[Environment]::GetFolderPath('Desktop'))){"
           "Remove-Item -LiteralPath (Join-Path $d 'LanDrop.lnk') -ErrorAction SilentlyContinue}")
    subprocess.Popen(f'cmd /c ping -n 3 127.0.0.1 >nul & rmdir /s /q "{INSTALL_DIR}"',
                     creationflags=NO_WINDOW, cwd=os.environ.get("TEMP", "C:\\"))
    msgbox("LanDrop sudah dihapus.")


# ---------------------------------------------------------------- main
def main():
    global S
    args = sys.argv[1:]
    if "--uninstall" in args:
        return uninstall()
    if "--install" in args and FROZEN:  # install tanpa dialog
        install()
        return
    if FROZEN and not is_installed_copy() and "--portable" not in args:
        r = msgbox(f"Install LanDrop {VERSION} di komputer ini?\n\n"
                   "• Shortcut di Desktop & Start Menu\n"
                   "• Otomatis jalan saat Windows menyala (bisa dimatikan)\n\n"
                   "Pilih 'No' untuk menjalankan tanpa install.", flags=0x03 | 0x20)
        if r == 6:
            if install():
                return
        elif r == 2:  # Cancel
            return
    background = "--background" in args
    if instance_running():
        if not background:
            open_window()
        return
    S = State()
    try:
        server = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), Handler)
    except OSError as e:
        msgbox(f"Port {HTTP_PORT} sedang dipakai aplikasi lain.\n\n{e}", flags=0x10)
        return
    server.daemon_threads = True
    threading.Thread(target=discovery_loop, daemon=True).start()
    threading.Thread(target=manual_loop, daemon=True).start()
    start_tray()
    if not background:
        threading.Timer(0.3, open_window).start()
    if not FROZEN:
        print(f"LanDrop berjalan di http://localhost:{HTTP_PORT}  (data: {DATA_DIR})")
    server.serve_forever()


if __name__ == "__main__":
    main()
