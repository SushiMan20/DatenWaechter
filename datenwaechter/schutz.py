"""Schutz für KI-Desktop-Apps (ChatGPT, Claude, Copilot, Perplexity): prüfen, BEVOR die App eine Datei bekommt.

1. Drop-Schutz: Zieht man eine Datei (aus Explorer, Desktop, Browser, Outlook …) über das Fenster einer KI-App,
   legt der Datenwächter eine Auffangfläche darüber. Die Datei landet bei ihm, wird geprüft und erst danach
   (Original oder geschwärzt) per Einfügen an die App übergeben.
2. „Datei öffnen“-Schutz: Im Windows-Dialog „Öffnen“ einer KI-App werden „Öffnen“, Enter und der Doppelklick
   auf eine Datei kurz angehalten. Unbedenkliches geht sofort durch; sonst fragt der Datenwächter und setzt auf
   Wunsch die geschwärzte Kopie in den Dialog ein – die App sieht das Original nie.

Umsetzung über Windows-Bordmittel: ein Maus- und Tastatur-Hook (WH_MOUSE_LL/WH_KEYBOARD_LL) entscheidet in
Mikrosekunden, ob eine Eingabe angehalten wird; alles Weitere passiert im Fenster-Thread. Grenzen: Apps mit
eigenem (nicht Windows-)Dateiauswahlfenster; die App muss Einfügen (Strg+V) von Dateien unterstützen.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .settings import path as settings_path

APPS = ("chatgpt.exe", "claude.exe", "copilot.exe", "perplexity.exe")
NAMEN = {"chatgpt.exe": "ChatGPT", "claude.exe": "Claude", "copilot.exe": "Copilot", "perplexity.exe": "Perplexity"}
QUELLEN = ("explorer.exe", "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "vivaldi.exe",
           "outlook.exe", "olk.exe", "thunderbird.exe", "totalcmd.exe", "totalcmd64.exe", "doublecmd.exe",
           "onedrive.exe", "ms-teams.exe", "teams.exe", "whatsapp.exe", "telegram.exe", "acrobat.exe",
           "acrord32.exe", "winword.exe", "excel.exe", "powerpnt.exe")
DATEIANSICHT = ("DirectUIHWND", "SysListView32")   # Explorer-Dateiliste bzw. Desktop
WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MOUSEMOVE = 0x0201, 0x0202, 0x0200
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_QUIT = 0x0100, 0x0101, 0x0104, 0x0012
VK_RETURN, VK_SPACE = 0x0D, 0x20
WM_GETTEXT, WM_GETTEXTLENGTH, WM_SETTEXT, WM_COMMAND, IDOK = 0x000D, 0x000E, 0x000C, 0x0111, 1
CMB13 = 0x47C   # Steuerelement „Dateiname“ im Windows-Dateidialog


# --------------------------------------------------------------------------- Einstellungen

def _einstellungen() -> dict:
    try:
        return json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def aktiv() -> bool:
    return bool(_einstellungen().get("ki_app_schutz", True))


def speichern(an: bool) -> None:
    p = settings_path()
    data = _einstellungen()
    data["ki_app_schutz"] = bool(an)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _liste(env: str, schluessel: str, standard: tuple) -> frozenset:
    roh = os.environ.get(env)
    if roh:
        return frozenset(x.strip().lower() for x in roh.split(",") if x.strip())
    eigene = _einstellungen().get(schluessel)
    return frozenset(x.lower() for x in eigene) if isinstance(eigene, list) else frozenset(standard)


def apps() -> frozenset:
    """Geschützte KI-Apps (Programmdateien). Test/Anpassung: DATENWAECHTER_SCHUTZ_APPS=a.exe,b.exe"""
    return _liste("DATENWAECHTER_SCHUTZ_APPS", "ki_apps", APPS)


def quellen() -> frozenset:
    return _liste("DATENWAECHTER_DRAG_QUELLEN", "drag_quellen", QUELLEN)


def app_name(exe: str) -> str:
    return NAMEN.get(exe.lower(), Path(exe).stem)


# --------------------------------------------------------------------------- Dateinamen aus dem Dialog (auch ohne Windows testbar)

def ordner_aus_adresse(text: str) -> Path | None:
    """„Adresse: C:\\Users\\a\\Downloads“ (Adressleiste des Dialogs) → Pfad; bekannte Ordnernamen → Pfad."""
    if not text:
        return None
    wert = text.split(": ", 1)[1] if ": " in text and not re.match(r"^[A-Za-z]:\\", text) else text
    wert = wert.strip()
    if re.match(r"^(?:[A-Za-z]:\\|\\\\)", wert):
        return Path(wert)
    home = Path.home()
    bekannt = {"desktop": "Desktop", "downloads": "Downloads", "dokumente": "Documents", "documents": "Documents",
               "bilder": "Pictures", "pictures": "Pictures", "musik": "Music", "music": "Music", "videos": "Videos"}
    letzter = re.split(r"[\\>]", wert)[-1].strip().lower()
    if letzter in bekannt:
        for basis in (home / bekannt[letzter], home / "OneDrive" / bekannt[letzter], home / letzter.capitalize()):
            if basis.is_dir():
                return basis
    return None


def namen_aus_feld(text: str) -> list[str]:
    """Inhalt des Felds „Dateiname“: ein Name, ein voller Pfad oder mehrere in Anführungszeichen."""
    text = (text or "").strip()
    if not text:
        return []
    mehrere = re.findall(r'"([^"]+)"', text)
    return mehrere if mehrere else [text.strip('"')]


def aufloesen(ordner: Path | None, name: str) -> Path | None:
    """Anzeigename → Datei/Ordner. Windows blendet Endungen oft aus („Vertrag“ statt „Vertrag.pdf“)."""
    p = Path(name)
    if p.is_absolute():
        return p if p.exists() else None
    if ordner is None or not ordner.is_dir():
        return None
    direkt = ordner / name
    if direkt.exists():
        return direkt
    try:
        passend = [c for c in ordner.iterdir() if c.is_file() and c.stem == name]
    except OSError:
        return None
    if not passend:
        return None
    return max(passend, key=lambda c: c.stat().st_mtime)   # gleicher Name, mehrere Endungen: die neueste


# --------------------------------------------------------------------------- Windows-Helfer

def _win():
    import ctypes
    from ctypes import wintypes
    return ctypes, wintypes, ctypes.windll.user32, ctypes.windll.kernel32


_PROZESSE: dict[int, str] = {}


def prozessname(pid: int) -> str:
    if pid in _PROZESSE:
        return _PROZESSE[pid]
    ctypes, wintypes, _u, k = _win()
    name = ""
    h = k.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        buf = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(520)
        if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            name = Path(buf.value).name.lower()
        k.CloseHandle(h)
    if len(_PROZESSE) > 500:
        _PROZESSE.clear()
    _PROZESSE[pid] = name
    return name


def fenster_pid(hwnd) -> int:
    ctypes, wintypes, u, _k = _win()
    pid = wintypes.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def klasse(hwnd) -> str:
    ctypes, _w, u, _k = _win()
    buf = ctypes.create_unicode_buffer(64)
    u.GetClassNameW(hwnd, buf, 64)
    return buf.value


def text(hwnd) -> str:
    """Text eines Fensters, auch in fremden Programmen (WM_GETTEXT wird von Windows übertragen)."""
    ctypes, _w, u, _k = _win()
    n = u.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
    buf = ctypes.create_unicode_buffer(n + 1)
    u.SendMessageW(hwnd, WM_GETTEXT, n + 1, buf)
    return buf.value


def setze_text(hwnd, wert: str) -> None:
    ctypes, _w, u, _k = _win()
    u.SendMessageW(hwnd, WM_SETTEXT, 0, ctypes.c_wchar_p(wert))


def wurzel(hwnd):
    _c, _w, u, _k = _win()
    return u.GetAncestor(hwnd, 2) or hwnd   # GA_ROOT


def kinder(hwnd) -> list:
    ctypes, wintypes, u, _k = _win()
    out = []
    Proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    u.EnumChildWindows(hwnd, Proc(lambda h, _l: out.append(h) or True), 0)
    return out


def rechteck(hwnd) -> tuple[int, int, int, int]:
    ctypes, wintypes, u, _k = _win()
    r = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


@dataclass
class Dialog:
    hwnd: int
    ok: int
    feld: int        # Eingabefeld „Dateiname“
    liste: int       # Dateiliste (DirectUIHWND) oder 0
    app: str         # z. B. "chatgpt.exe"

    def ordner(self) -> Path | None:
        """Aktueller Ordner aus der Adressleiste („Adresse: C:\\…“)."""
        for h in kinder(self.hwnd):
            if klasse(h) == "ToolbarWindow32":
                p = ordner_aus_adresse(text(h))
                if p is not None:
                    return p
        return None

    def feldtext(self) -> str:
        return text(self.feld)

    def oeffnen(self) -> None:
        """Wie ein Klick auf „Öffnen“ – aber als Nachricht, also nicht vom Hook angehalten."""
        _c, _w, u, _k = _win()
        u.PostMessageW(self.hwnd, WM_COMMAND, IDOK, self.ok)


def dateidialog(hwnd, erlaubt: frozenset | None = None) -> Dialog | None:
    """Ist hwnd (oder sein Hauptfenster) ein Windows-Dateidialog einer geschützten App?"""
    if not hwnd:
        return None
    _c, _w, u, _k = _win()
    root = wurzel(hwnd)
    if klasse(root) != "#32770":
        return None
    pid = fenster_pid(root)
    if pid == os.getpid():
        return None
    exe = prozessname(pid)
    if exe not in (erlaubt if erlaubt is not None else apps()):
        return None
    ok = u.GetDlgItem(root, IDOK)
    feld, liste = 0, 0
    for h in kinder(root):
        k = klasse(h)
        if not feld and u.GetDlgCtrlID(h) == CMB13 and k in ("ComboBoxEx32", "ComboBox", "Edit"):
            feld = h if k == "Edit" else next((c for c in kinder(h) if klasse(c) == "Edit"), 0)
        elif not liste and k == "DirectUIHWND" and klasse(u.GetParent(h)) == "SHELLDLL_DefView":
            liste = h
    if not ok or not feld:
        return None
    return Dialog(root, ok, feld, liste, exe)


def ausgewaehlt() -> str | None:
    """Name des gerade markierten Eintrags (UI Automation) – für den Doppelklick in der Dateiliste."""
    try:
        import comtypes.client
        uia = comtypes.client.GetModule("UIAutomationCore.dll")
        auto = comtypes.client.CreateObject("{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=uia.IUIAutomation)
        el = auto.GetFocusedElement()
        walker = auto.ControlViewWalker
        for _ in range(5):
            if el is None:
                return None
            if el.CurrentControlType in (50007, 50029):   # ListItem, DataItem
                return el.CurrentName or None
            el = walker.GetParentElement(el)
    except Exception:  # noqa: BLE001 – ohne UI Automation gibt es eine Rückfrage statt Raten
        return None
    return None


def nach_vorne(hwnd) -> None:
    """Fenster aktivieren – auch aus dem Hintergrund (Eingabe kurz mit dem aktiven Fenster verbinden)."""
    _c, _w, u, k = _win()
    if u.IsIconic(hwnd):
        u.ShowWindow(hwnd, 9)   # SW_RESTORE
    fg = u.GetForegroundWindow()
    fremd = u.GetWindowThreadProcessId(fg, None) if fg else 0
    eigen = k.GetCurrentThreadId()
    verbunden = bool(fremd and fremd != eigen and u.AttachThreadInput(eigen, fremd, True))
    try:
        u.BringWindowToTop(hwnd)
        u.SetForegroundWindow(hwnd)
    finally:
        if verbunden:
            u.AttachThreadInput(eigen, fremd, False)


def einfuegen(hwnd) -> None:
    """Zielfenster nach vorne holen und Strg+V senden (Inhalt liegt schon in der Zwischenablage)."""
    _c, _w, u, _k = _win()
    nach_vorne(hwnd)
    time.sleep(0.25)
    for vk, up in ((0x11, 0), (0x56, 0), (0x56, 2), (0x11, 2)):
        u.keybd_event(vk, 0, up, 0)


# --------------------------------------------------------------------------- Hook

class Waechter:
    """Maus- und Tastatur-Hook. callback(art, hwnd, extra) läuft im Hook-Thread (nur in eine Queue legen!).

    Arten: "dialog" (Öffnen/Enter angehalten), "dialog-doppelklick", "drop-zeigen" (Ziehen über eine KI-App),
    "drop-ende" (Maustaste losgelassen).
    """

    def __init__(self, callback):
        self.callback = callback
        self.error: str | None = None
        self._thread_id = None
        self._apps = apps()
        self._quellen = quellen()
        self._dialoge: dict[int, tuple[float, Dialog | None]] = {}
        self._schlucke_maus = False
        self._schlucke_taste = 0
        self._letzter_klick = None
        self._ziehen = None          # (x, y, Quelle ok?)
        self._ueber = None
        self._geprueft = 0.0
        if sys.platform != "win32":
            self.error = "nur unter Windows"
            return
        ready = threading.Event()
        threading.Thread(target=self._loop, args=(ready,), daemon=True, name="ki-app-schutz").start()
        ready.wait(2)

    @property
    def active(self) -> bool:
        return self.error is None and self._thread_id is not None

    def _dialog(self, hwnd) -> Dialog | None:
        """Dateidialog einer KI-App? (kurz zwischengespeichert, der Hook muss schnell sein)"""
        root = wurzel(hwnd)
        jetzt = time.monotonic()
        hit = self._dialoge.get(root)
        if hit and jetzt - hit[0] < 2:
            return hit[1]
        d = dateidialog(root, self._apps) if klasse(root) == "#32770" else None
        if len(self._dialoge) > 50:
            self._dialoge.clear()
        self._dialoge[root] = (jetzt, d)
        return d

    def _ist_app(self, root) -> bool:
        pid = fenster_pid(root)
        return pid != os.getpid() and prozessname(pid) in self._apps and klasse(root) != "#32770"

    def _loop(self, ready: threading.Event) -> None:
        ctypes, wintypes, u, k = _win()

        class MSLL(ctypes.Structure):
            _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

        class KBDLL(ctypes.Structure):
            _fields_ = [("vk", wintypes.DWORD), ("scan", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

        class GUITHREADINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("active", wintypes.HWND),
                        ("focus", wintypes.HWND), ("capture", wintypes.HWND), ("menuOwner", wintypes.HWND),
                        ("moveSize", wintypes.HWND), ("caret", wintypes.HWND), ("rcCaret", wintypes.RECT)]

        LRESULT = ctypes.c_ssize_t
        Proc = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        u.SetWindowsHookExW.argtypes = [ctypes.c_int, Proc, wintypes.HINSTANCE, wintypes.DWORD]
        u.SetWindowsHookExW.restype = wintypes.HHOOK
        u.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        u.CallNextHookEx.restype = LRESULT
        u.WindowFromPoint.argtypes = [wintypes.POINT]
        u.WindowFromPoint.restype = wintypes.HWND
        u.GetForegroundWindow.restype = wintypes.HWND
        k.GetModuleHandleW.restype = wintypes.HMODULE
        doppel_ms = u.GetDoubleClickTime()

        def cursor():
            # Logische Koordinaten (passen zu Fenstern und Tk, auch bei 125/150 % Skalierung)
            p = wintypes.POINT()
            u.GetCursorPos(ctypes.byref(p))
            return p

        def maus(n_code, w_param, l_param):
            try:
                if n_code >= 0:
                    if w_param == WM_LBUTTONDOWN:
                        info = ctypes.cast(l_param, ctypes.POINTER(MSLL)).contents
                        p = cursor()
                        hwnd = u.WindowFromPoint(p)
                        d = self._dialog(hwnd) if hwnd else None
                        last = self._letzter_klick
                        doppel = bool(last and info.time - last[2] <= doppel_ms and
                                      math.hypot(p.x - last[0], p.y - last[1]) <= 4)
                        self._letzter_klick = None if doppel else (p.x, p.y, info.time)
                        if d is not None:
                            if hwnd == d.ok:
                                self._schlucke_maus = True
                                self.callback("dialog", d.hwnd, None)
                                return 1
                            if doppel and d.liste and (hwnd == d.liste or u.IsChild(d.liste, hwnd)):
                                self._schlucke_maus = True
                                self.callback("dialog-doppelklick", d.hwnd, None)
                                return 1
                        quelle = False
                        if hwnd:
                            root = wurzel(hwnd)
                            exe = prozessname(fenster_pid(root))
                            quelle = (exe in self._quellen and exe not in self._apps and
                                      (exe != "explorer.exe" or klasse(hwnd) in DATEIANSICHT))
                        self._ziehen = (p.x, p.y, quelle)
                        self._ueber = None
                    elif w_param == WM_MOUSEMOVE and self._ziehen and self._ziehen[2]:
                        jetzt = time.monotonic()
                        if jetzt - self._geprueft > 0.04:
                            self._geprueft = jetzt
                            p = cursor()
                            if math.hypot(p.x - self._ziehen[0], p.y - self._ziehen[1]) > 12:
                                hwnd = u.WindowFromPoint(p)
                                root = wurzel(hwnd) if hwnd else None
                                if root and root != self._ueber:
                                    self._ueber = root
                                    if self._ist_app(root):
                                        self.callback("drop-zeigen", root, None)
                    elif w_param == WM_LBUTTONUP:
                        if self._schlucke_maus:
                            self._schlucke_maus = False
                            return 1
                        if self._ziehen and self._ueber:
                            self.callback("drop-ende", self._ueber, None)
                        self._ziehen = None
                        self._ueber = None
            except Exception:  # noqa: BLE001 – ein Fehler hier darf nie die Maus blockieren
                pass
            return u.CallNextHookEx(None, n_code, w_param, l_param)

        def taste(n_code, w_param, l_param):
            try:
                if n_code >= 0:
                    info = ctypes.cast(l_param, ctypes.POINTER(KBDLL)).contents
                    if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN) and info.vk in (VK_RETURN, VK_SPACE):
                        fg = u.GetForegroundWindow()
                        d = self._dialog(fg) if fg else None
                        if d is not None:
                            gti = GUITHREADINFO()
                            gti.cbSize = ctypes.sizeof(GUITHREADINFO)
                            u.GetGUIThreadInfo(u.GetWindowThreadProcessId(fg, None), ctypes.byref(gti))
                            f = gti.focus
                            in_liste = bool(d.liste and f and (f == d.liste or u.IsChild(d.liste, f)))
                            if (info.vk == VK_RETURN and (f == d.feld or f == d.ok or in_liste)) or \
                                    (info.vk == VK_SPACE and f == d.ok):
                                self._schlucke_taste = info.vk
                                self.callback("dialog-doppelklick" if in_liste else "dialog", d.hwnd, None)
                                return 1
                    elif w_param == WM_KEYUP and info.vk == self._schlucke_taste:
                        self._schlucke_taste = 0
                        return 1
            except Exception:  # noqa: BLE001
                pass
            return u.CallNextHookEx(None, n_code, w_param, l_param)

        self._procs = (Proc(maus), Proc(taste))   # Referenzen halten
        self._thread_id = k.GetCurrentThreadId()
        modul = k.GetModuleHandleW(None)
        hooks = [u.SetWindowsHookExW(14, self._procs[0], modul, 0), u.SetWindowsHookExW(13, self._procs[1], modul, 0)]
        if not all(hooks):
            self.error = "Maus-/Tastatur-Hook nicht verfügbar"
            for h in hooks:
                if h:
                    u.UnhookWindowsHookEx(h)
            self._thread_id = None
            ready.set()
            return
        ready.set()
        msg = wintypes.MSG()
        try:
            while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                u.TranslateMessage(ctypes.byref(msg))
                u.DispatchMessageW(ctypes.byref(msg))
        finally:
            for h in hooks:
                u.UnhookWindowsHookEx(h)

    def stop(self) -> None:
        if self._thread_id:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread_id = None
