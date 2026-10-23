# -*- coding: utf-8 -*-
"""
PC Time — счётчик времени за компьютером в системном трее (Windows).

• Иконка в трее показывает, сколько вы сегодня за ПК (часы + кольцо минут).
• Клик по иконке — панель: обзор (сегодня, сессия, неделя, рекорд, график)
  и вкладка «Приложения» с топом программ за сегодня / 7 дней / всё время.
• Уведомления в стиле игровых оверлеев: каждый час и напоминание о перерыве.
• Перед началом работы спрашивает разрешение. Ничего не отправляет в сеть.
  Данные лежат в %LOCALAPPDATA%\\PC Time\\stats.json.

Запуск из исходников:  pip install -r requirements.txt  →  pythonw pc_time.py
Сборка exe:            build.bat  (или GitHub Actions, см. README)
"""

import sys
import os
import json
import time
import shutil
import ctypes
import hashlib
import datetime as dt
from pathlib import Path
from collections import Counter

from PySide6.QtCore import (Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QPointF,
                            QRectF, QLockFile, QDir, QUrl, QParallelAnimationGroup, QObject,
                            Signal, QEvent, QFileInfo)
from PySide6.QtGui import (QIcon, QPixmap, QPainter, QColor, QFont, QPen, QPainterPath,
                           QAction, QDesktopServices, QGuiApplication, QLinearGradient,
                           QFontMetrics)
from PySide6.QtWidgets import (QApplication, QWidget, QDialog, QSystemTrayIcon, QMenu, QLabel,
                               QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout, QCheckBox,
                               QGraphicsDropShadowEffect, QFrame, QStackedWidget, QScrollArea,
                               QButtonGroup, QFileIconProvider)
from PySide6.QtNetwork import QLocalServer, QLocalSocket

APP_NAME = "PC Time"
APP_VERSION = "1.1.0"
CONSENT_VERSION = 2          # 2 — добавлен учёт по приложениям

# ─────────────────────────── Где хранятся данные ───────────────────────────
if getattr(sys, "frozen", False):          # собранный .exe
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent


def default_data_dir():
    if os.environ.get("PCTIME_DATA"):
        return Path(os.environ["PCTIME_DATA"])
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "PC Time"
    return Path.home() / ".local" / "share" / "pc-time"


DATA_DIR = default_data_dir()

# ─────────────────────────────── Палитра ───────────────────────────────────
BG = "#121316"
CARD = "#1b1d21"
CARD2 = "#24272c"
BORDER = "#2e3238"
TEXT = "#eceef1"
MUTED = "#8b9099"
GREEN = "#76b900"
GREEN2 = "#9be22d"
AMBER = "#f5a524"
RED = "#e5484d"

FONT = "Segoe UI"

QSS = f"""
* {{ font-family: '{FONT}', 'Inter', sans-serif; color: {TEXT}; }}
QFrame#card {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 16px; }}
QFrame#tile {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#segbar {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; }}
QLabel {{ background: transparent; }}
QLabel#muted {{ color: {MUTED}; font-size: 12px; }}
QLabel#caps {{ color: {MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QPushButton {{ background: {CARD2}; border: 1px solid {BORDER}; border-radius: 9px;
              padding: 10px 18px; font-size: 13px; font-weight: 600; }}
QPushButton:hover {{ background: #2c3036; }}
QPushButton#primary {{ background: {GREEN}; color: #0b0c0d; border: none; }}
QPushButton#primary:hover {{ background: {GREEN2}; }}
QPushButton#danger {{ background: {RED}; color: white; border: none; }}
QPushButton#danger:hover {{ background: #f06266; }}
QPushButton#ghost {{ background: transparent; border: none; color: {MUTED};
                    font-size: 15px; padding: 4px 8px; }}
QPushButton#ghost:hover {{ color: {TEXT}; }}
QPushButton#link {{ background: transparent; border: none; color: {GREEN}; padding: 0;
                   font-size: 12px; font-weight: 600; }}
QPushButton#link:hover {{ color: {GREEN2}; }}
QPushButton#seg {{ background: transparent; border: none; border-radius: 7px; color: {MUTED};
                  padding: 7px 10px; font-size: 12px; font-weight: 600; }}
QPushButton#seg:hover {{ color: {TEXT}; }}
QPushButton#seg:checked {{ background: {CARD2}; color: {TEXT}; }}
QCheckBox {{ spacing: 10px; font-size: 13px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px;
                       border: 1px solid #454a52; background: {CARD2}; }}
QCheckBox::indicator:checked {{ background: {GREEN}; border-color: {GREEN}; }}
QMenu {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 8px 24px 8px 12px; border-radius: 6px; font-size: 13px; }}
QMenu::item:selected {{ background: {CARD2}; }}
QMenu::item:disabled {{ color: {GREEN}; font-weight: 700; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 6px 8px; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 6px; margin: 2px 0; }}
QScrollBar::handle:vertical {{ background: #3a3f46; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #4a5058; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


# ─────────────────────────────── Утилиты ───────────────────────────────────
def fmt_time(sec):
    sec = int(sec)
    if 0 < sec < 60:
        return "< 1 мин"
    h, m = sec // 3600, (sec % 3600) // 60
    return f"{h} ч {m:02d} мин" if h else f"{m} мин"


def fmt_short(sec):
    sec = int(sec)
    return f"{sec // 3600}:{(sec % 3600) // 60:02d}"


def plural(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def plural_hours(n):
    return plural(n, "час", "часа", "часов")


def fmt_date(d):
    return f"{d.day} {MONTHS[d.month - 1]}"


def font(px, bold=False):
    f = QFont(FONT)
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def add_shadow(widget, blur=32, dy=8, alpha=170):
    e = QGraphicsDropShadowEffect(widget)
    e.setBlurRadius(blur)
    e.setOffset(0, dy)
    e.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(e)


def bottom_right(w, gap=6):
    geo = QGuiApplication.primaryScreen().availableGeometry()
    return QPoint(geo.right() + 1 - w.width() - gap, geo.bottom() + 1 - w.height() - gap)


# ──────────────────────────── Windows API ──────────────────────────────────
# Читается только: время последнего ввода (для простоя) и имя программы
# активного окна. Заголовки окон, сайты и нажатия клавиш НЕ читаются.
class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


if sys.platform == "win32":
    from ctypes import wintypes
    _user32 = ctypes.WinDLL("user32")
    _kernel32 = ctypes.WinDLL("kernel32")
    _version = ctypes.WinDLL("version")
    _user32.GetLastInputInfo.argtypes = [ctypes.POINTER(_LASTINPUTINFO)]
    _user32.GetLastInputInfo.restype = wintypes.BOOL
    _kernel32.GetTickCount.restype = wintypes.DWORD
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                     ctypes.POINTER(wintypes.DWORD)]
    _kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    _version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    _version.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    _version.GetFileVersionInfoW.restype = wintypes.BOOL
    _version.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p),
                                        ctypes.POINTER(wintypes.UINT)]
    _version.VerQueryValueW.restype = wintypes.BOOL


def idle_seconds():
    if sys.platform != "win32":
        return 0
    lii = _LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(lii)
    if not _user32.GetLastInputInfo(ctypes.byref(lii)):
        return 0
    return ((_kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF) / 1000.0


def _foreground_pid():
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return 0
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _process_path(pid):
    h = _kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        size = wintypes.DWORD(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
        return None
    finally:
        _kernel32.CloseHandle(h)


def file_description(path):
    """«Описание файла» из свойств exe — обычно это красивое имя программы."""
    try:
        size = _version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not _version.GetFileVersionInfoW(path, 0, size, buf):
            return None
        ptr, ln = ctypes.c_void_p(), wintypes.UINT()
        langs = []
        if _version.VerQueryValueW(buf, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(ln)) \
                and ln.value >= 4:
            w = ctypes.cast(ptr, ctypes.POINTER(wintypes.WORD))
            langs.append((w[0], w[1]))
        langs += [(0x0409, 0x04B0), (0x0419, 0x04B0), (0x0409, 0x04E4)]
        for lang, cp in langs:
            sub = f"\\StringFileInfo\\{lang:04x}{cp:04x}\\FileDescription"
            if _version.VerQueryValueW(buf, sub, ctypes.byref(ptr), ctypes.byref(ln)) and ln.value:
                s = ctypes.wstring_at(ptr.value, ln.value).split("\x00")[0].strip()
                if s:
                    return s
    except Exception:
        return None
    return None


# Красивые имена для программ, у которых «описание файла» неудачное
FRIENDLY = {
    "explorer.exe": "Проводник",
    "applicationframehost.exe": "Приложения Windows",
    "searchhost.exe": "Пуск и поиск",
    "searchapp.exe": "Пуск и поиск",
    "startmenuexperiencehost.exe": "Пуск и поиск",
    "shellexperiencehost.exe": "Панель задач Windows",
    "code.exe": "Visual Studio Code",
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Firefox",
    "opera.exe": "Opera",
    "browser.exe": "Яндекс Браузер",
    "telegram.exe": "Telegram",
    "discord.exe": "Discord",
    "steam.exe": "Steam",
    "steamwebhelper.exe": "Steam",
    "fl64.exe": "FL Studio",
    "fl.exe": "FL Studio",
    "winword.exe": "Word",
    "excel.exe": "Excel",
    "powerpnt.exe": "PowerPoint",
    "windowsterminal.exe": "Терминал",
    "cmd.exe": "Командная строка",
    "powershell.exe": "PowerShell",
    "taskmgr.exe": "Диспетчер задач",
    "screenclippinghost.exe": "Ножницы",
    "snippingtool.exe": "Ножницы",
    "pctime.exe": "PC Time",
    "pythonw.exe": "Python",
    "python.exe": "Python",
}
IGNORED = {"lockapp.exe", "logonui.exe"}   # экран блокировки — не считаем


class AppTracker:
    def __init__(self):
        self.cache = {}           # pid -> (key, name, path) | None
        self.cache_born = time.monotonic()

    def current(self):
        if sys.platform != "win32":
            return None
        if time.monotonic() - self.cache_born > 600 or len(self.cache) > 300:
            self.cache.clear()            # pid могут переиспользоваться — периодически сбрасываем
            self.cache_born = time.monotonic()
        try:
            pid = _foreground_pid()
            if not pid:
                return None
            if pid not in self.cache:
                self.cache[pid] = self._describe(pid)
            return self.cache[pid]
        except Exception:
            return None

    @staticmethod
    def _describe(pid):
        path = _process_path(pid)
        if not path:
            return None
        key = Path(path).name.lower()
        if key in IGNORED:
            return None
        name = FRIENDLY.get(key) or file_description(path) or Path(path).stem
        if len(name) > 48:
            name = name[:46] + "…"
        return key, name, path


# ─────────────────────────── Автозапуск с Windows ───────────────────────────
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _autostart_cmd():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return f'"{pyw if pyw.exists() else exe}" "{Path(__file__).resolve()}"'


def set_autostart(on):
    if sys.platform != "win32":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, _autostart_cmd())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


def get_autostart():
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


# ─────────────────────────────── Хранилище ─────────────────────────────────
def migrate_old_data(new_dir):
    """Версия 1.0 хранила данные в папке PCTime_data рядом с программой.
    Переносим их в новую папку один раз. Возвращает старую папку или None."""
    new_file = new_dir / "stats.json"
    if new_file.exists():
        return None
    home = Path.home()
    candidates = [BASE_DIR / "PCTime_data"]
    for desk in (home / "Desktop", home / "Рабочий стол", home / "OneDrive" / "Desktop",
                 home / "OneDrive" / "Рабочий стол"):
        candidates.append(desk / "PCTime_data")
    for folder in candidates:
        old = folder / "stats.json"
        try:
            if old.exists():
                new_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old, new_file)
                old.replace(folder / "stats.old.json")
                (folder / "ПЕРЕНЕСЕНО.txt").write_text(
                    f"PC Time перенёс статистику в папку:\n{new_dir}\n\nЭту папку можно удалить.\n", "utf-8")
                return folder
        except OSError:
            continue
    return None


class Store:
    DEFAULT_SETTINGS = {"notifications": True, "idle_pause": True, "track_apps": True,
                        "idle_minutes": 5, "break_hours": 2}

    def __init__(self, folder):
        self.folder = Path(folder)
        self.file = self.folder / "stats.json"
        self.migrated_from = migrate_old_data(self.folder)
        self.data = {"app": APP_NAME, "version": 2, "consent": False, "consent_version": 0,
                     "consent_date": None, "days": {}, "first_seen": {}, "apps": {},
                     "app_info": {}, "settings": dict(self.DEFAULT_SETTINGS)}
        if self.file.exists():
            try:
                loaded = json.loads(self.file.read_text("utf-8"))
                self.data.update(loaded)
                self.data["settings"] = {**self.DEFAULT_SETTINGS, **loaded.get("settings", {})}
                if loaded.get("consent") and "consent_version" not in loaded:
                    self.data["consent_version"] = 1
            except Exception:
                self.file.replace(self.file.with_name("stats.broken.json"))

    @property
    def consent(self):
        return bool(self.data.get("consent")) and self.data.get("consent_version", 0) >= CONSENT_VERSION

    @property
    def had_old_consent(self):
        return bool(self.data.get("consent")) and not self.consent

    @property
    def settings(self):
        return self.data["settings"]

    def save(self):
        if not self.consent:                 # без согласия ничего не пишем на диск
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        readme = self.folder / "ЧТО ЭТО.txt"
        if not readme.exists():
            readme.write_text(
                "Здесь PC Time хранит статистику времени за компьютером (stats.json).\n"
                "Данные никуда не отправляются. Смотреть статистику удобнее в самой программе —\n"
                "кликните по иконке в трее.\n", "utf-8")
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), "utf-8")
        os.replace(tmp, self.file)

    def add(self, secs, app=None):
        key = dt.date.today().isoformat()
        days = self.data["days"]
        if key not in days:
            days[key] = 0.0
            self.data["first_seen"][key] = dt.datetime.now().strftime("%H:%M")
        days[key] = round(days[key] + secs, 2)
        if app:
            per = self.data["apps"].setdefault(key, {})
            per[app] = round(per.get(app, 0.0) + secs, 2)
        return days[key]

    def set_app_info(self, key, name, path):
        info = self.data["app_info"].get(key)
        if not info or info.get("name") != name or info.get("path") != path:
            self.data["app_info"][key] = {"name": name, "path": path}

    def app_name(self, key):
        return self.data["app_info"].get(key, {}).get("name") or key

    def app_path(self, key):
        return self.data["app_info"].get(key, {}).get("path")

    def get(self, date):
        return self.data["days"].get(date.isoformat(), 0.0)

    def today(self):
        return self.get(dt.date.today())

    def first_seen_today(self):
        return self.data["first_seen"].get(dt.date.today().isoformat())

    def last_days(self, n=7):
        t = dt.date.today()
        return [(t - dt.timedelta(days=i)) for i in range(n - 1, -1, -1)]

    def all_days(self):
        return [dt.date.fromisoformat(k) for k in sorted(self.data["days"])]

    def apps_total(self, dates):
        c = Counter()
        for d in dates:
            c.update(self.data["apps"].get(d.isoformat(), {}))
        return c

    def total(self, dates):
        return sum(self.get(d) for d in dates)

    def record(self):
        days = self.data["days"]
        if not days:
            return None, 0
        k = max(days, key=days.get)
        return dt.date.fromisoformat(k), days[k]

    def clear(self):
        self.data["days"] = {}
        self.data["first_seen"] = {}
        self.data["apps"] = {}
        self.save()


# ─────────────────────────────── Рисование ─────────────────────────────────
def paint_ring(p, r, frac, color, width, track="#2a2e34"):
    p.save()
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(track), width, Qt.SolidLine, Qt.RoundCap))
    p.drawEllipse(r)
    if frac > 0:
        p.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, 90 * 16, -int(360 * 16 * min(frac, 1.0)))
    p.restore()


def paint_clock(p, r, color):
    p.save()
    p.setBrush(Qt.NoBrush)
    w = max(1.6, r.width() * 0.09)
    p.setPen(QPen(QColor(color), w, Qt.SolidLine, Qt.RoundCap))
    p.drawEllipse(r.adjusted(w / 2, w / 2, -w / 2, -w / 2))
    c = r.center()
    p.drawLine(c, QPointF(c.x(), r.top() + r.height() * 0.27))
    p.drawLine(c, QPointF(c.x() + r.width() * 0.2, c.y() + r.height() * 0.1))
    p.restore()


def paint_cup(p, r, color):
    p.save()
    p.setBrush(Qt.NoBrush)
    w = max(1.6, r.width() * 0.08)
    p.setPen(QPen(QColor(color), w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    x, y, s = r.x(), r.y(), r.width()
    body = QPainterPath()
    body.moveTo(x + s * 0.15, y + s * 0.42)
    body.lineTo(x + s * 0.70, y + s * 0.42)
    body.lineTo(x + s * 0.64, y + s * 0.82)
    body.quadTo(x + s * 0.62, y + s * 0.9, x + s * 0.54, y + s * 0.9)
    body.lineTo(x + s * 0.31, y + s * 0.9)
    body.quadTo(x + s * 0.23, y + s * 0.9, x + s * 0.21, y + s * 0.82)
    body.closeSubpath()
    p.drawPath(body)
    p.drawArc(QRectF(x + s * 0.6, y + s * 0.48, s * 0.26, s * 0.24), 90 * 16, -180 * 16)
    for dx in (0.3, 0.45, 0.6):
        st = QPainterPath()
        st.moveTo(x + s * dx, y + s * 0.32)
        st.cubicTo(x + s * (dx - 0.06), y + s * 0.24, x + s * (dx + 0.06), y + s * 0.18, x + s * dx, y + s * 0.1)
        p.drawPath(st)
    p.restore()


def paint_check(p, r, color, width=2.2):
    p.save()
    p.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    path.moveTo(r.x() + r.width() * 0.22, r.y() + r.height() * 0.52)
    path.lineTo(r.x() + r.width() * 0.43, r.y() + r.height() * 0.72)
    path.lineTo(r.x() + r.width() * 0.78, r.y() + r.height() * 0.32)
    p.drawPath(path)
    p.restore()


def make_tray_icon(seconds, state="on"):
    """Иконка трея: цифра — часы (или минуты, если меньше часа), кольцо — минуты текущего часа."""
    s = 64
    pm = QPixmap(s, s)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    h, m = int(seconds) // 3600, (int(seconds) % 3600) // 60
    col = {"on": GREEN, "idle": AMBER, "paused": MUTED}[state]
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(BG))
    p.drawEllipse(QRectF(2, 2, 60, 60))
    paint_ring(p, QRectF(6, 6, 52, 52), m / 60, col, 7, track="#3b4048")
    txt = f"{h}ч" if h else f"{m}м"
    p.setFont(font(26 if len(txt) <= 2 else 20, True))
    p.setPen(QColor(TEXT if state == "on" else col))
    p.drawText(QRectF(0, 0, s, s), Qt.AlignCenter, txt)
    p.end()
    return QIcon(pm)


class LogoWidget(QWidget):
    def __init__(self, size=30, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setToolTip(f"{APP_NAME} {APP_VERSION}")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.NoPen)
        c = QColor(GREEN)
        c.setAlpha(40)
        p.setBrush(c)
        p.drawRoundedRect(r, 8, 8)
        paint_clock(p, r.adjusted(6, 6, -6, -6), GREEN)


# ────────────────────────────── Уведомления ────────────────────────────────
class ToastCard(QWidget):
    def __init__(self, title, text, kind, parent=None):
        super().__init__(parent)
        self.title, self.text, self.kind = title, text, kind
        self.accent = AMBER if kind == "break" else GREEN
        self.progress = 1.0
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = QRectF(0.5, 0.5, w - 1, h - 1)
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        p.fillPath(path, QColor(CARD))
        p.setClipPath(path)
        acc = QColor(self.accent)
        g = QLinearGradient(0, 0, 170, 0)
        c1 = QColor(acc); c1.setAlpha(46)
        c2 = QColor(acc); c2.setAlpha(0)
        g.setColorAt(0, c1)
        g.setColorAt(1, c2)
        p.fillRect(QRectF(0, 0, 170, h), g)
        p.fillRect(QRectF(0, 0, 4, h), acc)
        ir = QRectF(24, (h - 3) / 2 - 18, 36, 36)
        bg = QColor(acc); bg.setAlpha(34)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawEllipse(ir.adjusted(-7, -7, 7, 7))
        (paint_cup if self.kind == "break" else paint_clock)(p, ir.adjusted(4, 4, -4, -4), self.accent)
        x = 86
        f = font(10, True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        p.setFont(f)
        p.setPen(acc)
        p.drawText(QRectF(x, 12, w - x - 16, 14), Qt.AlignLeft | Qt.AlignVCenter, "PC TIME")
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(x, 12, w - x - 16, 14), Qt.AlignRight | Qt.AlignVCenter,
                   dt.datetime.now().strftime("%H:%M"))
        p.setFont(font(15, True))
        p.setPen(QColor(TEXT))
        p.drawText(QRectF(x, 28, w - x - 16, 22), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        p.setFont(font(12))
        p.setPen(QColor("#a7acb4"))
        p.drawText(QRectF(x, 51, w - x - 16, h - 58), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, self.text)
        p.fillRect(QRectF(0, h - 3, w, 3), QColor("#2a2e34"))
        p.fillRect(QRectF(0, h - 3, w * self.progress, 3), acc)


class Toast(QWidget):
    closed = Signal(object)
    clicked = Signal()
    M = 16  # поля под тень

    def __init__(self, title, text, kind="info", duration=7000):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.card = ToastCard(title, text, kind, self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(self.M, self.M, self.M, self.M)
        lay.addWidget(self.card)
        add_shadow(self.card, 30, 6, 180)
        self.setFixedSize(370 + 2 * self.M, 100 + 2 * self.M)
        self.duration, self.elapsed, self.hover, self.dying = duration, 0, False, False
        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._tick)
        self._anims = []

    def _animate(self, pos_from, pos_to, op_from, op_to, ms, done=None):
        grp = QParallelAnimationGroup(self)
        a = QPropertyAnimation(self, b"pos")
        a.setStartValue(pos_from); a.setEndValue(pos_to)
        a.setDuration(ms); a.setEasingCurve(QEasingCurve.OutCubic)
        b = QPropertyAnimation(self, b"windowOpacity")
        b.setStartValue(op_from); b.setEndValue(op_to); b.setDuration(ms)
        grp.addAnimation(a); grp.addAnimation(b)
        if done:
            grp.finished.connect(done)
        self._anims.append(grp)
        grp.start()

    def popup(self, target):
        self.target = target
        self.setWindowOpacity(0)
        self.move(target + QPoint(70, 0))
        self.show()
        self._animate(target + QPoint(70, 0), target, 0.0, 1.0, 380)
        self.timer.start()

    def move_to(self, target):
        if self.dying:
            return
        self.target = target
        a = QPropertyAnimation(self, b"pos", self)
        a.setEndValue(target); a.setDuration(260); a.setEasingCurve(QEasingCurve.OutCubic)
        self._anims.append(a)
        a.start()

    def _tick(self):
        if self.hover:
            return
        self.elapsed += 30
        self.card.progress = max(0.0, 1 - self.elapsed / self.duration)
        self.card.update()
        if self.elapsed >= self.duration:
            self.dismiss()

    def dismiss(self):
        if self.dying:
            return
        self.dying = True
        self.timer.stop()
        self._animate(self.pos(), self.pos() + QPoint(70, 0), self.windowOpacity(), 0.0, 260, self._finish)

    def _finish(self):
        self.closed.emit(self)
        self.close()

    def enterEvent(self, e):
        self.hover = True

    def leaveEvent(self, e):
        self.hover = False

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        self.dismiss()


class ToastManager(QObject):
    def __init__(self):
        super().__init__()
        self.toasts = []

    def show(self, title, text, kind="info", on_click=None):
        t = Toast(title, text, kind)
        if on_click:
            t.clicked.connect(on_click)
        t.closed.connect(self._remove)
        self.toasts.append(t)
        alive = [x for x in self.toasts if not x.dying]
        if len(alive) > 3:
            alive[0].dismiss()
        self._relayout(new=t)

    def _targets(self):
        geo = QGuiApplication.primaryScreen().availableGeometry()
        y = geo.bottom() + 1
        res = {}
        for t in reversed([x for x in self.toasts if not x.dying]):
            top = y - t.height()
            res[t] = QPoint(geo.right() + 1 - t.width(), top)
            y = top + 2 * Toast.M - 10
        return res

    def _relayout(self, new=None):
        for t, pos in self._targets().items():
            if t is new:
                t.popup(pos)
            else:
                t.move_to(pos)

    def _remove(self, t):
        if t in self.toasts:
            self.toasts.remove(t)
        self._relayout()


# ─────────────────────────── Панель статистики ─────────────────────────────
class HeroRing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(128, 128)
        self.frac, self.color = 0.0, GREEN

    def set(self, frac, color):
        self.frac, self.color = frac, color
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(10, 10, 108, 108)
        glow = QColor(self.color); glow.setAlpha(45)
        p.setPen(QPen(glow, 20, Qt.SolidLine, Qt.RoundCap))
        if self.frac > 0:
            p.drawArc(r, 90 * 16, -int(360 * 16 * min(self.frac, 1)))
        paint_ring(p, r, self.frac, self.color, 10, track="#24282e")
        p.setPen(QColor(TEXT))
        p.setFont(font(26, True))
        pct = self.frac * 100
        pct_txt = f"{pct:.1f}".replace(".", ",") if pct < 10 else f"{pct:.0f}"
        p.drawText(QRectF(0, 34, 128, 36), Qt.AlignCenter, f"{pct_txt}%")
        p.setPen(QColor(MUTED))
        p.setFont(font(11))
        p.drawText(QRectF(0, 68, 128, 18), Qt.AlignCenter, "суток")


class WeekChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setMouseTracking(True)
        self.items = []     # (подпись, секунды, сегодня?, дата)
        self.hover = -1

    def set_items(self, items):
        self.items = items
        self.update()

    def _slot(self):
        return self.width() / max(1, len(self.items))

    def paintEvent(self, e):
        if not self.items:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        top, bottom = 26, h - 24
        maxv = max(max(v for _, v, _, _ in self.items), 3600)
        p.setPen(QPen(QColor("#22262b"), 1, Qt.DashLine))
        for k in (0, 0.5, 1):
            y = bottom - (bottom - top) * k
            p.drawLine(QPointF(0, y), QPointF(w, y))
        slot = self._slot()
        bw = min(28, slot * 0.52)
        for i, (lab, v, today, _) in enumerate(self.items):
            x = slot * i + (slot - bw) / 2
            bh = (bottom - top) * v / maxv
            if v > 0:
                bh = max(bh, 4)
            rect = QRectF(x, bottom - bh, bw, bh)
            if today:
                g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
                g.setColorAt(0, QColor(GREEN2)); g.setColorAt(1, QColor(GREEN))
                brush = g
            else:
                brush = QColor("#4a5058" if i == self.hover else "#33383f")
            path = QPainterPath()
            path.addRoundedRect(rect, min(6, bw / 2), min(6, bw / 2))
            p.fillPath(path, brush)
            p.setFont(font(11, today))
            p.setPen(QColor(GREEN if today else MUTED))
            p.drawText(QRectF(slot * i, bottom + 4, slot, 18), Qt.AlignCenter, lab)
            if i == self.hover or (today and self.hover == -1):
                p.setFont(font(11, True))
                p.setPen(QColor(TEXT))
                p.drawText(QRectF(slot * i - 10, bottom - bh - 22, slot + 20, 18), Qt.AlignCenter,
                           fmt_short(v))

    def mouseMoveEvent(self, e):
        i = int(e.position().x() // self._slot())
        if 0 <= i < len(self.items) and i != self.hover:
            self.hover = i
            _, v, _, d = self.items[i]
            self.setToolTip(f"{WEEKDAYS[d.weekday()]}, {fmt_date(d)} — {fmt_time(v)}")
            self.update()

    def leaveEvent(self, e):
        self.hover = -1
        self.update()


class Tile(QFrame):
    def __init__(self, caption, parent=None):
        super().__init__(parent)
        self.setObjectName("tile")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(2)
        c = QLabel(caption.upper()); c.setObjectName("caps")
        self.value = QLabel("—"); self.value.setFont(font(18, True))
        self.sub = QLabel(""); self.sub.setObjectName("muted")
        lay.addWidget(c); lay.addWidget(self.value); lay.addWidget(self.sub)

    def set(self, value, sub=""):
        self.value.setText(value)
        self.sub.setText(sub)


class Segmented(QFrame):
    """Переключатель-«таблетка»: Обзор | Приложения, Сегодня | 7 дней | Всё время."""
    changed = Signal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setObjectName("segbar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        for i, text in enumerate(labels):
            b = QPushButton(text)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.group.addButton(b, i)
            lay.addWidget(b, 1)
        self.group.button(0).setChecked(True)
        self.group.idClicked.connect(self.changed.emit)


# ── иконки приложений ──
_icon_provider = None
_icon_cache = {}
AVATAR_COLORS = ["#4c6ef5", "#12b886", "#f59f00", "#e64980", "#7950f2", "#15aabf", "#fa5252", "#82c91e"]


def app_icon(key, path, name, size=28):
    ck = (key, size)
    if ck in _icon_cache:
        return _icon_cache[ck]
    global _icon_provider
    pm = None
    if path and os.path.exists(path):
        if _icon_provider is None:
            _icon_provider = QFileIconProvider()
        ic = _icon_provider.icon(QFileInfo(path))
        if not ic.isNull():
            pm = ic.pixmap(size * 2, size * 2)
            if pm.isNull():
                pm = None
    if pm is None:                     # нет иконки — кружок с первой буквой
        pm = QPixmap(size * 2, size * 2)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        idx = int(hashlib.md5(key.encode()).hexdigest(), 16) % len(AVATAR_COLORS)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(AVATAR_COLORS[idx]))
        p.drawRoundedRect(QRectF(0, 0, size * 2, size * 2), size * 0.5, size * 0.5)
        p.setPen(QColor("white"))
        p.setFont(font(int(size * 1.0), True))
        p.drawText(QRectF(0, 0, size * 2, size * 2), Qt.AlignCenter, (name or "?")[:1].upper())
        p.end()
    _icon_cache[ck] = pm
    return pm


class AppList(QWidget):
    """Топ приложений: иконка, название, время, полоска и процент."""
    ROW = 50

    def __init__(self, parent=None):
        super().__init__(parent)
        self.entries = []     # dict(key, name, secs, path, kind)
        self.total = 1
        self.setMouseTracking(True)

    def set_entries(self, entries, total):
        self.entries, self.total = entries, max(total, 1)
        self.setFixedHeight(max(1, len(entries)) * self.ROW)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w = self.width() - 8
        maxv = max([x["secs"] for x in self.entries if x["kind"] == "app"] or [1])
        fm_name = QFontMetrics(font(13, True))
        for i, it in enumerate(self.entries):
            y = i * self.ROW
            icon_r = QRectF(0, y + 10, 28, 28)
            if it["kind"] == "app":
                pm = app_icon(it["key"], it["path"], it["name"])
                p.drawPixmap(icon_r, pm, QRectF(pm.rect()))
            else:
                p.setPen(QPen(QColor("#4a5058"), 1.5, Qt.DashLine))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(icon_r.adjusted(1, 1, -1, -1), 8, 8)
                p.setPen(QColor(MUTED))
                p.setFont(font(13, True))
                p.drawText(icon_r, Qt.AlignCenter, "…" if it["kind"] == "other" else "?")
            x = 42
            p.setFont(font(13, True))
            p.setPen(QColor(TEXT if it["kind"] == "app" else MUTED))
            p.drawText(QRectF(x, y + 6, w - x - 100, 20), Qt.AlignLeft | Qt.AlignVCenter,
                       fm_name.elidedText(it["name"], Qt.ElideRight, int(w - x - 104)))
            p.setFont(font(12, True))
            p.setPen(QColor(TEXT))
            p.drawText(QRectF(w - 100, y + 6, 100, 20), Qt.AlignRight | Qt.AlignVCenter, fmt_time(it["secs"]))
            # полоска
            bar = QRectF(x, y + 31, w - x - 46, 6)
            track = QPainterPath(); track.addRoundedRect(bar, 3, 3)
            p.fillPath(track, QColor("#262a30"))
            frac = it["secs"] / maxv if it["kind"] == "app" else it["secs"] / self.total
            if frac > 0:
                fill_r = QRectF(bar.x(), bar.y(), max(6, bar.width() * min(frac, 1)), bar.height())
                fill = QPainterPath(); fill.addRoundedRect(fill_r, 3, 3)
                if it["kind"] == "app":
                    g = QLinearGradient(fill_r.topLeft(), fill_r.topRight())
                    g.setColorAt(0, QColor(GREEN)); g.setColorAt(1, QColor(GREEN2 if i == 0 else GREEN))
                    p.fillPath(fill, g)
                else:
                    p.fillPath(fill, QColor("#4a5058"))
            p.setFont(font(11))
            p.setPen(QColor(MUTED))
            pct = it["secs"] / self.total * 100
            p.drawText(QRectF(w - 42, y + 25, 42, 18), Qt.AlignRight | Qt.AlignVCenter,
                       f"{pct:.0f}%" if pct >= 1 else "<1%")

    def mouseMoveEvent(self, e):
        i = int(e.position().y() // self.ROW)
        if 0 <= i < len(self.entries):
            it = self.entries[i]
            tip = f"{it['name']} — {fmt_time(it['secs'])}"
            if it.get("hint"):
                tip += f"\n{it['hint']}"
            elif it["kind"] == "app":
                tip += f"\n{it['key']}"
            self.setToolTip(tip)


class AppsPage(QWidget):
    PERIODS = ["Сегодня", "7 дней", "Всё время"]

    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self.ctrl = ctrl
        self.period = 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self.seg = Segmented(self.PERIODS)
        self.seg.changed.connect(self._set_period)
        lay.addWidget(self.seg)

        box = QFrame(); box.setObjectName("tile")
        bl = QVBoxLayout(box); bl.setContentsMargins(14, 12, 8, 10); bl.setSpacing(8)
        head = QHBoxLayout()
        cap = QLabel("ТОП ПРИЛОЖЕНИЙ"); cap.setObjectName("caps")
        self.summary = QLabel(); self.summary.setObjectName("muted")
        head.addWidget(cap); head.addStretch(); head.addWidget(self.summary); head.addSpacing(6)
        bl.addLayout(head)

        self.empty = QLabel(); self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignCenter); self.empty.setWordWrap(True)
        self.list = AppList()
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.list)
        self.scroll.setMinimumHeight(120)
        bl.addWidget(self.empty, 1)
        bl.addWidget(self.scroll, 1)
        lay.addWidget(box, 1)

        self.hint = QLabel("Учитывается только имя программы — без заголовков окон и сайтов.")
        self.hint.setObjectName("muted"); self.hint.setWordWrap(True)
        lay.addWidget(self.hint)

    def _set_period(self, i):
        self.period = i
        self.refresh()

    def refresh(self):
        st = self.ctrl.store
        if self.period == 0:
            dates = [dt.date.today()]
        elif self.period == 1:
            dates = st.last_days(7)
        else:
            dates = st.all_days() or [dt.date.today()]
        per = st.apps_total(dates)
        total = st.total(dates)
        tracked = sum(per.values())
        items = sorted(per.items(), key=lambda kv: kv[1], reverse=True)
        top, rest = items[:12], items[12:]
        entries = [{"key": k, "name": st.app_name(k), "path": st.app_path(k), "secs": v, "kind": "app"}
                   for k, v in top if v >= 1]
        if rest:
            n = len(rest)
            entries.append({"key": "", "name": f"Остальные ({n})", "path": None, "kind": "other",
                            "secs": sum(v for _, v in rest),
                            "hint": ", ".join(st.app_name(k) for k, _ in rest[:8])})
        untracked = total - tracked
        if untracked >= 60:
            entries.append({"key": "", "name": "Без разбивки", "path": None, "kind": "none",
                            "secs": untracked,
                            "hint": "Время до включения учёта приложений\nили когда программу не удалось определить"})

        apps_n = len(items)
        self.summary.setText(f"{fmt_time(total)} · {apps_n} {plural(apps_n, 'приложение', 'приложения', 'приложений')}"
                             if apps_n else fmt_time(total))
        if not st.settings.get("track_apps", True) and not items:
            self.empty.setText("Учёт приложений выключен.\nВключить: правый клик по иконке в трее → «Учёт по приложениям».")
            entries = []
        elif not items:
            self.empty.setText("Пока нет данных.\nПоработайте пару минут — здесь появится топ программ.")
            entries = []
        self.empty.setVisible(not entries)
        self.scroll.setVisible(bool(entries))
        self.list.set_entries(entries, total)


class StatsPanel(QWidget):
    def __init__(self, ctrl):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.ctrl = ctrl
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.hidden_at = 0.0
        self._anims = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        card = QFrame(); card.setObjectName("card")
        add_shadow(card, 40, 10, 190)
        outer.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 18)
        lay.setSpacing(14)

        # шапка
        head = QHBoxLayout(); head.setSpacing(10)
        head.addWidget(LogoWidget(30))
        title = QLabel(APP_NAME); title.setFont(font(16, True))
        head.addWidget(title)
        self.status = QLabel()
        head.addWidget(self.status)
        head.addStretch()
        close = QPushButton("✕"); close.setObjectName("ghost"); close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.hide_panel)
        head.addWidget(close)
        lay.addLayout(head)

        self.tabs = Segmented(["Обзор", "Приложения"])
        self.tabs.changed.connect(self._switch)
        lay.addWidget(self.tabs)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_overview())
        self.apps_page = AppsPage(ctrl)
        self.stack.addWidget(self.apps_page)
        lay.addWidget(self.stack, 1)

        # подвал
        foot = QHBoxLayout()
        lock = QLabel("🔒  Данные хранятся только на этом ПК"); lock.setObjectName("muted")
        foot.addWidget(lock); foot.addStretch()
        open_btn = QPushButton("Открыть папку"); open_btn.setObjectName("link")
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.clicked.connect(ctrl.open_folder)
        foot.addWidget(open_btn)
        lay.addLayout(foot)

        self.setFixedWidth(440)
        self.adjustSize()

    def _build_overview(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        hero = QHBoxLayout(); hero.setSpacing(18)
        self.ring = HeroRing()
        hero.addWidget(self.ring)
        col = QVBoxLayout(); col.setSpacing(2); col.addStretch()
        cap = QLabel("СЕГОДНЯ ЗА КОМПЬЮТЕРОМ"); cap.setObjectName("caps")
        self.today_lbl = QLabel(); self.today_lbl.setFont(font(30, True))
        self.today_sub = QLabel(); self.today_sub.setObjectName("muted")
        self.today_top = QLabel(); self.today_top.setObjectName("muted")
        col.addWidget(cap); col.addWidget(self.today_lbl); col.addWidget(self.today_sub)
        col.addWidget(self.today_top)
        col.addStretch()
        hero.addLayout(col, 1)
        lay.addLayout(hero)

        grid = QGridLayout(); grid.setSpacing(10)
        self.t_session = Tile("Сессия")
        self.t_week = Tile("Неделя")
        self.t_avg = Tile("Среднее")
        self.t_rec = Tile("Рекорд")
        for i, t in enumerate((self.t_session, self.t_week, self.t_avg, self.t_rec)):
            grid.addWidget(t, i // 2, i % 2)
        lay.addLayout(grid)

        chart_box = QFrame(); chart_box.setObjectName("tile")
        cb = QVBoxLayout(chart_box); cb.setContentsMargins(14, 12, 14, 8)
        c2 = QLabel("ПОСЛЕДНИЕ 7 ДНЕЙ"); c2.setObjectName("caps")
        self.chart = WeekChart()
        cb.addWidget(c2); cb.addWidget(self.chart)
        lay.addWidget(chart_box)
        return page

    def _switch(self, i):
        self.stack.setCurrentIndex(i)
        self.refresh()

    def refresh(self):
        c, st = self.ctrl, self.ctrl.store
        state = c.state()
        color = {"on": GREEN, "idle": AMBER, "paused": MUTED}[state]
        text = {"on": "● идёт отсчёт", "idle": "● простой", "paused": "❚❚ пауза"}[state]
        self.status.setText(text)
        self.status.setStyleSheet(f"color:{color}; font-size:12px; font-weight:600; padding-left:4px;")
        if self.stack.currentIndex() == 1:
            self.apps_page.refresh()
            return

        today = st.today()
        self.ring.set(today / 86400, color)
        self.today_lbl.setText(fmt_time(today))
        first = st.first_seen_today()
        self.today_sub.setText(f"Первое включение сегодня — {first}" if first else "Отсчёт только начался")
        top = st.apps_total([dt.date.today()]).most_common(1)
        if top:
            self.today_top.setText(f"Больше всего: {st.app_name(top[0][0])}")
            self.today_top.show()
        else:
            self.today_top.hide()

        self.t_session.set(fmt_time(c.session), f"с {c.session_start.strftime('%H:%M')}")
        days = st.last_days(7)
        vals = [st.get(d) for d in days]
        self.t_week.set(fmt_time(sum(vals)), "за 7 дней")
        active = [v for v in vals if v > 60]
        self.t_avg.set(fmt_time(sum(active) / len(active)) if active else "—", "в день, за неделю")
        rd, rv = st.record()
        self.t_rec.set(fmt_time(rv) if rd else "—", fmt_date(rd) if rd else "пока нет")
        t = dt.date.today()
        self.chart.set_items([(WEEKDAYS[d.weekday()], v, d == t, d) for d, v in zip(days, vals)])

    def toggle(self):
        if self.isVisible():
            self.hide_panel()
        elif time.monotonic() - self.hidden_at > 0.35:   # клик по трею сам закрыл панель
            self.show_panel()

    def show_panel(self, tab=None):
        if tab is not None:
            self.tabs.group.button(tab).setChecked(True)
            self.stack.setCurrentIndex(tab)
        self.refresh()
        self.adjustSize()
        target = bottom_right(self, 0)
        self.setWindowOpacity(0)
        self.move(target + QPoint(0, 30))
        self.show()
        self.raise_()
        self.activateWindow()
        grp = QParallelAnimationGroup(self)
        a = QPropertyAnimation(self, b"pos"); a.setStartValue(target + QPoint(0, 30))
        a.setEndValue(target); a.setDuration(280); a.setEasingCurve(QEasingCurve.OutCubic)
        b = QPropertyAnimation(self, b"windowOpacity"); b.setStartValue(0.0); b.setEndValue(1.0)
        b.setDuration(220)
        grp.addAnimation(a); grp.addAnimation(b)
        self._anims = [grp]
        grp.start()

    def hide_panel(self):
        self.hidden_at = time.monotonic()
        self.hide()

    def event(self, e):
        if e.type() == QEvent.WindowDeactivate and self.isVisible():
            self.hide_panel()
        return super().event(e)


# ──────────────────────────────── Диалоги ──────────────────────────────────
class StyledDialog(QDialog):
    def __init__(self, width=520):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle(APP_NAME)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        self.card = QFrame(); self.card.setObjectName("card")
        add_shadow(self.card, 44, 12, 200)
        outer.addWidget(self.card)
        self.body = QVBoxLayout(self.card)
        self.body.setContentsMargins(30, 28, 30, 26)
        self.body.setSpacing(14)
        self.setFixedWidth(width)
        self._drag = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None

    def buttons(self, cancel_text, ok_text, ok_style="primary"):
        row = QHBoxLayout(); row.addStretch()
        cancel = QPushButton(cancel_text); cancel.setCursor(Qt.PointingHandCursor)
        ok = QPushButton(ok_text); ok.setObjectName(ok_style); ok.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject); ok.clicked.connect(self.accept)
        row.addWidget(cancel); row.addWidget(ok)
        self.body.addSpacing(6)
        self.body.addLayout(row)
        ok.setDefault(True)


class ShieldIcon(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 64)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = QColor(GREEN); bg.setAlpha(36)
        p.setPen(Qt.NoPen); p.setBrush(bg)
        p.drawRoundedRect(QRectF(0, 0, 64, 64), 18, 18)
        path = QPainterPath()
        path.moveTo(32, 13)
        path.lineTo(48, 19)
        path.cubicTo(48, 34, 43, 45, 32, 51)
        path.cubicTo(21, 45, 16, 34, 16, 19)
        path.closeSubpath()
        g = QLinearGradient(0, 13, 0, 51)
        g.setColorAt(0, QColor(GREEN2)); g.setColorAt(1, QColor(GREEN))
        p.fillPath(path, g)
        paint_check(p, QRectF(21, 20, 22, 22), "#0b0c0d", 3)


class CheckDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(GREEN); c.setAlpha(40)
        p.setPen(Qt.NoPen); p.setBrush(c)
        p.drawEllipse(QRectF(0, 0, 20, 20))
        paint_check(p, QRectF(2, 2, 16, 16), GREEN, 2)


class ConsentDialog(StyledDialog):
    def __init__(self, data_file, update=False):
        super().__init__(560)
        self.body.addWidget(ShieldIcon())
        if update:
            t = QLabel("PC Time обновился"); t.setFont(font(22, True))
            sub = ("Теперь программа умеет показывать, в каких приложениях вы проводите больше всего времени. "
                   "Это новый вид данных, поэтому нужно ваше разрешение ещё раз. Накопленная статистика сохранится.")
        else:
            t = QLabel("Разрешить вести статистику?"); t.setFont(font(22, True))
            sub = ("PC Time считает, сколько времени вы проводите за компьютером, "
                   "и показывает это в панели задач. Прежде чем начать, вот что важно знать:")
        self.body.addWidget(t)
        s = QLabel(sub)
        s.setWordWrap(True); s.setStyleSheet(f"color:{MUTED}; font-size:13px;")
        self.body.addWidget(s)

        points = [
            "Собирается <b>время за ПК по дням</b> и, если разрешите ниже, <b>имя активной программы</b> "
            "(например, chrome.exe). Заголовки окон, сайты, скриншоты и нажатия клавиш <b>не записываются</b>.",
            "<b>Ничего не отправляется</b> в интернет — у программы вообще нет сетевых функций.",
            f"Всё хранится <b>в папке на вашем компьютере</b>:<br>"
            f"<span style='color:{MUTED}'>{data_file.parent}</span>",
            "Удалить данные или отозвать разрешение можно <b>в любой момент</b> "
            "через меню иконки в трее.",
        ]
        for txt in points:
            row = QHBoxLayout(); row.setSpacing(12)
            dot = CheckDot(); row.addWidget(dot, 0, Qt.AlignTop)
            l = QLabel(txt); l.setWordWrap(True); l.setTextFormat(Qt.RichText)
            l.setStyleSheet("font-size:13px;")
            row.addWidget(l, 1)
            self.body.addLayout(row)

        line = QFrame(); line.setFixedHeight(1); line.setStyleSheet(f"background:{BORDER};")
        self.body.addSpacing(4); self.body.addWidget(line)
        self.apps = QCheckBox("Считать время по приложениям (топ программ)")
        self.apps.setChecked(True)
        self.autostart = QCheckBox("Запускать вместе с Windows")
        self.autostart.setChecked(True)
        self.idle = QCheckBox("Не считать время, когда я отошёл (нет активности 5+ минут)")
        self.idle.setChecked(True)
        for cb in (self.apps, self.autostart, self.idle):
            self.body.addWidget(cb)
        self.buttons("Не разрешать и выйти" if update else "Не разрешать", "Разрешить и начать")


class ConfirmDialog(StyledDialog):
    def __init__(self, title, text, ok_text, danger=True):
        super().__init__(440)
        t = QLabel(title); t.setFont(font(18, True)); t.setWordWrap(True)
        s = QLabel(text); s.setWordWrap(True); s.setStyleSheet(f"color:{MUTED}; font-size:13px;")
        self.body.addWidget(t); self.body.addWidget(s)
        self.buttons("Отмена", ok_text, "danger" if danger else "primary")


# ─────────────────────────────── Контроллер ────────────────────────────────
class PCTime(QObject):
    def __init__(self, qapp):
        super().__init__()
        self.qapp = qapp
        self.store = Store(DATA_DIR)
        self.toasts = ToastManager()
        self.tracker = AppTracker()
        self.session = 0.0
        self.continuous = 0.0
        self.session_start = dt.datetime.now()
        self.paused = False
        self.idle = False
        self._icon_key = None
        self.panel = None

    # запуск
    def run(self):
        first = False
        if not self.store.consent:
            update = self.store.had_old_consent
            dlg = ConsentDialog(self.store.file, update=update)
            if dlg.exec() != QDialog.Accepted:
                return False
            self.store.data["consent"] = True
            self.store.data["consent_version"] = CONSENT_VERSION
            self.store.data["consent_date"] = dt.datetime.now().isoformat(timespec="seconds")
            self.store.settings["idle_pause"] = dlg.idle.isChecked()
            self.store.settings["track_apps"] = dlg.apps.isChecked()
            self.store.save()
            try:
                set_autostart(dlg.autostart.isChecked())
            except OSError:
                pass
            first = "update" if update else "new"
        else:
            try:
                if get_autostart():
                    set_autostart(True)      # обновить путь, если программу перенесли (например, .py → .exe)
            except OSError:
                pass
        self._start(first)
        return True

    def _start(self, first):
        self.last_hour = int(self.store.today() // 3600)
        self.panel = StatsPanel(self)

        self.tray = QSystemTrayIcon(make_tray_icon(self.store.today()))
        self.tray.activated.connect(self._on_tray)
        self.tray.setContextMenu(self._build_menu())
        self.tray.show()

        self._last = time.monotonic()
        self.tick_timer = QTimer(self); self.tick_timer.setInterval(1000)
        self.tick_timer.timeout.connect(self._tick); self.tick_timer.start()
        self.save_timer = QTimer(self); self.save_timer.setInterval(15000)
        self.save_timer.timeout.connect(self.store.save); self.save_timer.start()
        self.qapp.aboutToQuit.connect(self.store.save)
        self._update_tray(force=True)

        if self.store.migrated_from:
            self.store.save()
            self.notify("Данные перенесены",
                        f"Статистика теперь хранится в системной папке. "
                        f"Старую папку PCTime_data можно удалить.",
                        on_click=self.open_folder)
        if first == "new":
            self.notify("Готово! PC Time работает",
                        "Иконка в трее показывает время за сегодня. Нажмите на неё, чтобы открыть статистику.")
        elif first == "update":
            self.notify("Новое: топ приложений",
                        "Откройте панель и перейдите на вкладку «Приложения».",
                        on_click=lambda: self.panel.show_panel(tab=1))
        elif self.store.today() > 60:
            self.notify("С возвращением!", f"Сегодня вы уже провели за компьютером {fmt_time(self.store.today())}.")
        else:
            self.notify("Отсчёт начался", "Хорошего дня! Время за ПК видно на иконке в трее.")

    def _build_menu(self):
        m = QMenu()
        self.a_head = m.addAction("")
        self.a_head.setEnabled(False)
        m.addSeparator()
        m.addAction("Открыть статистику", lambda: self.panel.show_panel(tab=0))
        m.addAction("Топ приложений", lambda: self.panel.show_panel(tab=1))
        m.addSeparator()
        s = self.store.settings
        self.a_pause = self._check(m, "Пауза отсчёта", False, self._set_pause)
        self._check(m, "Уведомления", s["notifications"], lambda v: self._set("notifications", v))
        self._check(m, "Учёт по приложениям", s["track_apps"], lambda v: self._set("track_apps", v))
        self._check(m, "Не считать простой", s["idle_pause"], lambda v: self._set("idle_pause", v))
        if sys.platform == "win32":
            self._check(m, "Запуск вместе с Windows", get_autostart(), set_autostart)
        m.addSeparator()
        m.addAction("Открыть папку с данными", self.open_folder)
        m.addAction("Удалить статистику…", self._ask_clear)
        m.addAction("Отозвать разрешение…", self._ask_revoke)
        m.addSeparator()
        m.addAction("Выход", self.qapp.quit)
        m.aboutToShow.connect(lambda: self.a_head.setText(f"Сегодня: {fmt_time(self.store.today())}"))
        self._menu = m
        return m

    def _check(self, menu, text, value, slot):
        a = QAction(text, menu, checkable=True)
        a.setChecked(value)
        a.toggled.connect(slot)
        menu.addAction(a)
        return a

    def _set(self, key, value):
        self.store.settings[key] = value
        self.store.save()

    def _set_pause(self, v):
        self.paused = v
        self._update_tray(force=True)

    def _on_tray(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.panel.toggle()

    # основной цикл
    def state(self):
        if self.paused:
            return "paused"
        return "idle" if self.idle else "on"

    def _tick(self):
        now = time.monotonic()
        delta, self._last = now - self._last, now
        if delta > 10 or delta < 0:      # компьютер спал / завис — эти секунды не считаем
            delta = 0
        if not self.paused:
            s = self.store.settings
            idle_now = s["idle_pause"] and idle_seconds() >= s["idle_minutes"] * 60
            if idle_now != self.idle:
                self.idle = idle_now
                if idle_now:
                    self.continuous = 0      # отошёл от компа — это и есть перерыв
            if not self.idle and delta:
                app_key = None
                if s.get("track_apps", True):
                    cur = self.tracker.current()
                    if cur:
                        app_key, name, path = cur
                        self.store.set_app_info(app_key, name, path)
                today = self.store.add(delta, app_key)
                self.session += delta
                self.continuous += delta
                self._milestones(today)
        self._update_tray()
        if self.panel.isVisible():
            self.panel.refresh()

    def _milestones(self, today):
        h = int(today // 3600)
        if h > self.last_hour:
            self.last_hour = h
            top = self.store.apps_total([dt.date.today()]).most_common(1)
            top_txt = f" Больше всего — {self.store.app_name(top[0][0])}." if top else ""
            if h == 1:
                self.notify("Первый час за компьютером", "Сегодня набежал ровно час." + top_txt)
            else:
                self.notify(f"{h} {plural_hours(h)} за компьютером",
                            f"Сегодня уже {fmt_time(today)}." + top_txt)
        if self.continuous >= self.store.settings["break_hours"] * 3600:
            self.continuous = 0
            self.notify("Время размяться",
                        f"Вы без перерыва уже {self.store.settings['break_hours']} ч. Встаньте, "
                        "потянитесь и дайте глазам отдохнуть пару минут.", kind="break")

    def _update_tray(self, force=False):
        today = self.store.today()
        key = (int(today // 60), self.state())
        if key == self._icon_key and not force:
            return
        self._icon_key = key
        self.tray.setIcon(make_tray_icon(today, self.state()))
        extra = {"on": "", "idle": "\n(простой — время не идёт)", "paused": "\n(пауза)"}[self.state()]
        self.tray.setToolTip(f"{APP_NAME}\nСегодня: {fmt_time(today)}\nСессия: {fmt_time(self.session)}{extra}")

    # действия
    def notify(self, title, text, kind="info", on_click=None):
        if self.store.settings.get("notifications", True):
            self.toasts.show(title, text, kind, on_click=on_click or (lambda: self.panel.show_panel()))

    def show_from_outside(self):
        if self.panel:
            self.panel.show_panel()

    def open_folder(self):
        self.store.save()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA_DIR)))

    def _ask_clear(self):
        d = ConfirmDialog("Удалить всю статистику?",
                          "Все накопленные дни и данные по приложениям будут стёрты без возможности "
                          "восстановления. Отсчёт продолжится с нуля.", "Удалить")
        if d.exec() == QDialog.Accepted:
            self.store.clear()
            self.session = self.continuous = 0
            self.last_hour = 0
            self._update_tray(force=True)
            self.notify("Статистика удалена", "Начинаем с чистого листа.")

    def _ask_revoke(self):
        d = ConfirmDialog("Отозвать разрешение?",
                          "Файл со статистикой будет удалён, автозапуск выключен, а программа закроется. "
                          "При следующем запуске она снова спросит разрешение.", "Отозвать и выйти")
        if d.exec() == QDialog.Accepted:
            self.save_timer.stop()
            self.store.data["consent"] = False
            try:
                self.qapp.aboutToQuit.disconnect(self.store.save)
            except (RuntimeError, TypeError):
                pass
            for f in (self.store.file, self.store.file.with_suffix(".tmp")):
                if f.exists():
                    f.unlink()
            try:
                set_autostart(False)
            except OSError:
                pass
            self.qapp.quit()


# ─────────────────────────────────── main ──────────────────────────────────
SERVER_NAME = "PCTime-" + (os.environ.get("USERNAME") or os.environ.get("USER") or "user")


def main():
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PCTime.Tracker")
        except Exception:
            pass
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setApplicationName(APP_NAME)
    qapp.setApplicationVersion(APP_VERSION)
    qapp.setStyleSheet(QSS)

    # Уже запущена? Тогда просто просим её показать панель и выходим.
    lock = QLockFile(os.path.join(QDir.tempPath(), "pc_time.lock"))
    if not lock.tryLock(100):
        sock = QLocalSocket()
        sock.connectToServer(SERVER_NAME)
        if sock.waitForConnected(500):
            sock.write(b"show")
            sock.flush()
            sock.waitForBytesWritten(500)
        sys.exit(0)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("Системный трей недоступен")
        sys.exit(1)

    ctrl = PCTime(qapp)

    server = QLocalServer()
    QLocalServer.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)
    def _on_conn():
        conn = server.nextPendingConnection()
        if conn:
            conn.disconnected.connect(conn.deleteLater)
        ctrl.show_from_outside()
    server.newConnection.connect(_on_conn)

    if not ctrl.run():
        sys.exit(0)
    qapp.setWindowIcon(make_tray_icon(0))
    sys.exit(qapp.exec())


if __name__ == "__main__":
    main()
