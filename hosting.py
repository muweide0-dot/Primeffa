#!/usr/bin/env python3
"""PrimeFFA Hosting Console – lokale 24/7-Konsole für den Bot.

Features:
- Start / Stop / Restart mit Live-Konsole (Logs in Echtzeit)
- Auto-Restart bei Absturz, Windows-Autostart, Bot läuft nach Schließen weiter
- Ordner-Buttons für alle Bot-Daten (DB, Logs, Transkripte, Projekt)
- Animierter Babyblauer Hintergrund (wandernder Verlauf + schwebende Blasen)
- Status-Punkt mit Puls-Animation

Start:  python hosting.py        (oder Doppelklick auf start-hosting.bat)
Test:   python hosting.py --selftest / --smoke
"""

from __future__ import annotations

import math
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

# tkinter fehlt oft auf Servern/Cloud-Hostern -> Ersatz, damit web.py
# hosting.py trotzdem importieren kann (GUI wird dort nie geöffnet).
try:
    import tkinter as tk
    from tkinter import messagebox, ttk
    HAS_TK = True
except ImportError:
    HAS_TK = False

    class _GuiUnavailable:
        """Platzhalter: erzeugt beim Benutzen einen klaren Fehler."""
        def __getattr__(self, name: str):
            class _Unavailable:
                def __init__(self, *a, **k):
                    raise RuntimeError(
                        "tkinter ist auf diesem System nicht verfügbar "
                        "(Hosting-GUI nur lokal nutzbar)."
                    )
            return _Unavailable

    tk = _GuiUnavailable()
    messagebox = _GuiUnavailable()
    ttk = _GuiUnavailable()

try:
    import winreg
except ImportError:  # nicht unter Windows
    winreg = None

BASE_DIR = Path(__file__).resolve().parent
BOT_SCRIPT = BASE_DIR / "bot.py"
LOG_FILE = BASE_DIR / "logs" / "bot.log"
DATA_DIR = BASE_DIR / "data"
DB_FILE = DATA_DIR / "primeffa.db"
TRANSCRIPT_DIR = BASE_DIR / "transcripts"
PACK_BAT = BASE_DIR / "pack.bat"
PYTHON = sys.executable

# Gemeinsame Stopp-Dateien (auch von web.py genutzt)
STOP_REQUEST = DATA_DIR / "shutdown.request"   # Bot führt sauberen Logout aus
STOP_FLAG = DATA_DIR / "bot.stopped"           # "manuell gestoppt" (shared)

AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "PrimeFFA-Hosting"

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ---------------------------------------------------------------- Farben
C_MAIN = "#89CFF0"   # Babyblau
C_LIGHT = "#BFEFFF"  # hell
C_DARK = "#5DADE2"   # Akzent
C_PANEL = "#FFFFFF"
C_SOFT = "#F7FCFF"
C_TEXT = "#17384F"
C_MUTED = "#5B7C93"
C_CONSOLE_BG = "#0E1B2C"
C_CONSOLE_FG = "#BFEFFF"
C_GREEN = "#57F287"
C_RED = "#ED4245"
C_YELLOW = "#FEE75C"
GRAD_TOP = "#F8FDFF"
GRAD_BOT = "#D6EFFD"


# =============================================================== Prozesse
def find_bot_processes() -> list[int]:
    """Alle Python-Prozesse finden, die bot.py ausführen (Windows + POSIX)."""
    if os.name != "nt":
        return _find_bot_processes_posix()
    cmd = (
        "Get-CimInstance Win32_Process -Filter \""
        "Name='python.exe' OR Name='pythonw.exe'\" | "
        "Where-Object { $_.CommandLine -like '*bot.py*' } | "
        "ForEach-Object { $_.ProcessId }"
    )
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW,
            timeout=25,
        )
        return [int(x) for x in (out.stdout or "").split() if x.strip().isdigit()]
    except Exception:
        return []


def _find_bot_processes_posix() -> list[int]:
    """Linux (via /proc) bzw. macOS (via ps): Prozesse mit bot.py finden."""
    pids: list[int] = []
    proc = Path("/proc")
    if proc.is_dir():
        for entry in os.listdir(proc):
            if not entry.isdigit():
                continue
            pid = int(entry)
            if pid == os.getpid():
                continue
            try:
                raw = (proc / entry / "cmdline").read_bytes()
            except OSError:
                continue
            cmd = raw.replace(b"\0", b" ").decode("utf-8", "replace")
            if "bot.py" in cmd and "python" in cmd:
                pids.append(pid)
        return sorted(pids)
    try:
        out = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=25,
        )
        for line in (out.stdout or "").splitlines():
            parts = line.strip().split(None, 1)
            if len(parts) == 2 and parts[0].isdigit():
                if "bot.py" in parts[1] and "python" in parts[1]:
                    pids.append(int(parts[0]))
    except Exception:
        return []
    return sorted(set(pids))


def _posix_pid_alive(pid: int) -> bool:
    """Nur POSIX: prüft, ob die PID noch läuft.

    Achtung: auf Windows würde os.kill(pid, 0) den Prozess beenden!
    """
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def kill_processes(pids: list[int]) -> int:
    """Beendet die angegebenen Prozesse. Anzahl beendeter Prozesse."""
    if os.name != "nt":
        import signal
        killed = 0
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
                killed += 1
            except OSError:
                pass
        deadline = time.time() + 3.0
        while time.time() < deadline and any(_posix_pid_alive(p) for p in pids):
            time.sleep(0.2)
        for pid in pids:                      # Fallback: hart
            if _posix_pid_alive(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        return killed
    killed = 0
    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                creationflags=CREATE_NO_WINDOW,
                timeout=15,
            )
            killed += 1
        except Exception:
            pass
    return killed


def start_bot_process() -> int | None:
    """Startet den Bot als Hintergrund-Prozess (Output → logs/hosting.log)."""
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    # Start erlaubt: shared Stopp-Flag und Shutdown-Anforderung entfernen
    for f in (STOP_FLAG, STOP_REQUEST):
        try:
            f.unlink()
        except OSError:
            pass
    try:
        fh = open(log_dir / "hosting.log", "ab", buffering=0)
        proc = subprocess.Popen(
            [PYTHON, str(BOT_SCRIPT)],
            cwd=str(BASE_DIR),
            stdin=subprocess.DEVNULL,
            stdout=fh,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_NO_WINDOW,
        )
        fh.close()
        return proc.pid
    except Exception:
        return None


def stop_bot_processes(grace: float = 8.0) -> tuple[bool, list[int]]:
    """Stoppt den Bot SAUBER (Discord-Logout) und hart nur als Fallback.

    Gibt (sauber_gestoppt, verbleibende_pids) zurück.
    """
    pids = find_bot_processes()
    if not pids:
        return True, []

    # 1) Sauberen Shutdown anfordern – bot.py meldet sich bei Discord ab,
    #    damit der Bot im Server sofort offline wird (kein "hängt noch an").
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        STOP_REQUEST.write_text("stop", encoding="utf-8")
    except OSError:
        pass

    deadline = time.time() + grace
    while time.time() < deadline:
        if not find_bot_processes():
            try:
                STOP_REQUEST.unlink()
            except OSError:
                pass
            return True, []
        time.sleep(0.4)

    # 2) Fallback: hart beenden
    left = find_bot_processes()
    if left:
        kill_processes(left)
        for _ in range(15):
            if not find_bot_processes():
                break
            time.sleep(0.4)
    try:
        STOP_REQUEST.unlink()
    except OSError:
        pass
    return False, find_bot_processes()


def mark_manually_stopped(on: bool) -> None:
    """Shared Flag: 'Bot ist manuell gestoppt' – alle Wachhunde respektieren das."""
    try:
        if on:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            STOP_FLAG.write_text("stopped", encoding="utf-8")
        else:
            STOP_FLAG.unlink()
    except OSError:
        pass


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n / 1:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def path_size(p: Path) -> int:
    if p.is_file():
        return p.stat().st_size
    if p.is_dir():
        total = 0
        for f in p.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError:
                pass
        return total
    return 0


# ------------------------------------------------------------ Autostart
def find_pythonw() -> str:
    cand = Path(sys.executable).with_name("pythonw.exe")
    return str(cand) if cand.exists() else sys.executable


def autostart_get() -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
            winreg.QueryValueEx(key, AUTOSTART_NAME)
        return True
    except OSError:
        return False


def autostart_set(on: bool) -> None:
    if winreg is None:
        return
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        if on:
            value = f'"{find_pythonw()}" "{Path(__file__).resolve()}"'
            winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, value)
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_NAME)
            except FileNotFoundError:
                pass


def autostart_get_named(name: str) -> bool:
    """Prüft einen beliebigen Autostart-Eintrag (z. B. 'PrimeFFA-Web')."""
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY) as key:
            winreg.QueryValueEx(key, name)
        return True
    except OSError:
        return False


def autostart_set_named(name: str, on: bool, script: str | None = None) -> None:
    """Setzt/löscht einen benannten Autostart-Eintrag (Standard: dieses Skript)."""
    if winreg is None:
        return
    target = script or str(Path(__file__).resolve())
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        if on:
            value = f'"{find_pythonw()}" "{target}"'
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        else:
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass


def open_path(p: Path) -> None:
    """Ordner im Explorer öffnen – nur lokal unter Windows sinnvoll."""
    opener = getattr(os, "startfile", None)   # existiert nur unter Windows
    if opener is None:
        return
    try:
        opener(str(p))  # noqa: S606
    except OSError:
        pass


# ====================================================== Hintergrund-Design
def lerp_hex(c1: str, c2: str, t: float) -> str:
    t = max(0.0, min(1.0, t))
    a = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
    return "#{:02X}{:02X}{:02X}".format(*(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))


class BubbleBackground(tk.Canvas):
    """Animierter Hintergrund: wandernder Farbverlauf + schwebende Blasen."""

    BUBBLE_COLORS = ("#FFFFFF", "#EAF7FF", "#D9F1FE", "#C9EBFD", "#BFEFFF")

    def __init__(self, master, **kw):
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("bd", 0)
        super().__init__(master, **kw)
        self.strips: list[int] = []
        self.strip_h = 6
        self.phase = 0.0
        self.tick = 0
        self.bubbles: list[dict] = []
        self._resize_job = None
        self.bind("<Configure>", self._on_resize)
        self._seed_bubbles()
        self.after(30, self._loop)

    # ---------------------------------------------------------- Blasen
    def _seed_bubbles(self) -> None:
        import random

        for _ in range(18):
            r = random.randint(6, 34)
            self.bubbles.append(
                {
                    "r": r,
                    "x": random.uniform(0.05, 0.95),
                    "y": random.uniform(0.0, 1.0),
                    "speed": random.uniform(0.0006, 0.0022),
                    "amp": random.uniform(0.004, 0.018),
                    "phase": random.uniform(0, math.tau),
                    "color": random.choice(self.BUBBLE_COLORS),
                    "id": None,
                }
            )

    # -------------------------------------------------------- Verlauf
    def _on_resize(self, event=None) -> None:
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(140, self._rebuild)

    def _rebuild(self) -> None:
        self._resize_job = None
        w = max(self.winfo_width(), 2)
        h = max(self.winfo_height(), 2)
        self.delete("strip")
        self.strips = []
        self.strip_h = max(4, h // 110)
        n = h // self.strip_h + 1
        for i in range(n):
            y0 = i * self.strip_h
            y1 = min(y0 + self.strip_h, h)
            color = lerp_hex(GRAD_TOP, GRAD_BOT, i / max(1, n - 1))
            item = self.create_rectangle(
                0, y0, w, y1, fill=color, outline="", tags="strip"
            )
            self.strips.append(item)
        # Blasen neu platzieren (Größe brauchen wir)
        for b in self.bubbles:
            if b["id"] is None:
                b["id"] = self.create_oval(
                    0, 0, 1, 1, fill=b["color"], outline="", tags="bubble"
            )
            self.tag_raise(b["id"])
        self._paint_strips()

    def _paint_strips(self) -> None:
        if not self.strips:
            return
        h = max(self.winfo_height(), 2)
        n = len(self.strips)
        for i, item in enumerate(self.strips):
            y = (i * self.strip_h) / h
            # wandernde Helligkeitswelle über den Verlauf
            wobble = 0.16 * math.sin(self.phase * 1.6 - y * 6.5)
            t = i / max(1, n - 1)
            t = max(0.0, min(1.0, t + wobble * 0.35))
            color = lerp_hex(GRAD_TOP, GRAD_BOT, t)
            self.itemconfig(item, fill=color)

    # ------------------------------------------------------ Animationsloop
    def _loop(self) -> None:
        try:
            if self.winfo_exists() and self.winfo_viewable():
                self.phase += 0.035
                self.tick += 1
                if self.tick % 5 == 0:
                    self._paint_strips()
                self._move_bubbles()
        except tk.TclError:
            return
        self.after(40, self._loop)

    def _move_bubbles(self) -> None:
        w = max(self.winfo_width(), 2)
        h = max(self.winfo_height(), 2)
        for b in self.bubbles:
            b["y"] -= b["speed"]
            if b["y"] < -0.08:
                b["y"] = 1.08
                b["x"] = min(0.97, max(0.03, b["x"] + 0.13)) if b["x"] < 0.5 else 0.05
            x = b["x"] + b["amp"] * math.sin(self.phase * 1.2 + b["phase"])
            r = b["r"]
            cx, cy = x * w, b["y"] * h
            if b["id"] is not None:
                self.coords(b["id"], cx - r, cy - r, cx + r, cy + r)


class PulseDot(tk.Canvas):
    """Status-Punkt mit Puls-Animation (grün = läuft, rot = gestoppt)."""

    STATES = {
        "running": (C_GREEN, "#8FF7B8"),
        "stopped": (C_RED, "#FF9B9B"),
        "starting": (C_YELLOW, "#FFF3B0"),
    }

    def __init__(self, master, size: int = 34):
        super().__init__(master, width=size, height=size, highlightthickness=0, bd=0)
        self.size = size
        self.state = "stopped"
        self.t = 0.0
        self.halo = self.create_oval(0, 0, 1, 1, outline="", fill="")
        self.dot = self.create_oval(0, 0, 1, 1, outline="", fill=C_RED)
        self.after(40, self._loop)

    def set_state(self, state: str) -> None:
        self.state = state

    def pulse(self) -> None:
        """Kurze Welle beim erfolgreichen Start."""
        self.t = 0.0
        self.state = "running"

    def _loop(self) -> None:
        try:
            if not self.winfo_exists():
                return
            self.t += 0.12
            base, halo = self.STATES.get(self.state, self.STATES["stopped"])
            wave = (math.sin(self.t) + 1) / 2          # 0..1
            c = self.size / 2
            r = 7 + wave * 2.5
            hr = 10 + wave * 6
            if self.state == "starting" and int(self.t * 2) % 2 == 0:
                base, halo = "#FFE08A", "#FFF7D6"
            self.itemconfig(self.dot, fill=base)
            self.itemconfig(self.halo, fill=halo)
            self.coords(self.halo, c - hr, c - hr, c + hr, c + hr)
            self.coords(self.dot, c - r, c - r, c + r, c + r)
        except tk.TclError:
            return
        self.after(40, self._loop)


class HoverButton(tk.Button):
    """Button mit sanftem Hover-Effekt."""

    def __init__(self, master, *, base: str, hover: str, **kw):
        kw.setdefault("relief", "flat")
        kw.setdefault("bd", 0)
        kw.setdefault("cursor", "hand2")
        kw.setdefault("padx", 14)
        kw.setdefault("pady", 7)
        kw.setdefault("activebackground", hover)
        super().__init__(master, bg=base, **kw)
        self._base = base
        self._hover = hover
        self.bind("<Enter>", lambda e: self.config(bg=self._hover))
        self.bind("<Leave>", lambda e: self.config(bg=self._base))


# =============================================================== Konsole
class HostingApp(tk.Tk):
    def __init__(self, auto_boot: bool = True) -> None:
        super().__init__()
        self.title("PrimeFFA Hosting Console")
        self.geometry("980x680")
        self.minsize(840, 560)
        self.configure(bg=GRAD_TOP)

        self.q: queue.Queue = queue.Queue()
        self.stop_workers = threading.Event()
        self.tail_pos: int | None = None
        self.proc_pid: int | None = None
        self.known_pids: list[int] = []
        self.since: float | None = None
        self.busy = False
        self.manual_off = False   # True = User hat Stop gedrückt
        self.restart_attempts = 0
        self.last_ok_since = 0.0

        self.auto_restart = tk.BooleanVar(value=True)
        self.keep_running = tk.BooleanVar(value=True)
        self.autostart_var = tk.BooleanVar(value=autostart_get())

        self._build_ui()

        threading.Thread(target=self._status_worker, daemon=True).start()
        threading.Thread(target=self._tail_worker, daemon=True).start()
        self.after(250, self._drain)
        self.after(1000, self._tick_ui)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._log("[Konsole] PrimeFFA Hosting Console gestartet.")
        if auto_boot:
            self.after(700, self.action_start)

    # ------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        # ttk-Style zuerst (Progressbar braucht das Layout vor der Erstellung)
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure(
            "Horizontal.TProgressbar", troughcolor="#E6F4FD",
            background=C_MAIN, thickness=6,
        )

        self.bg = BubbleBackground(self)
        self.bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        # -------- Kopfzeile
        head = tk.Frame(self, bg=C_MAIN, height=52)
        head.pack(fill="x")
        head.pack_propagate(False)
        tk.Label(
            head, text="🩵  PrimeFFA Hosting Console",
            bg=C_MAIN, fg="#FFFFFF", font=("Segoe UI", 14, "bold"),
        ).pack(side="left", padx=16)
        tk.Label(
            head, text="lokal · 24/7 · Babyblau",
            bg=C_MAIN, fg="#EAF8FF", font=("Segoe UI", 10),
        ).pack(side="right", padx=16)

        # -------- Status-Panel
        status = tk.Frame(self, bg=C_PANEL, highlightthickness=0)
        status.pack(fill="x", padx=16, pady=(12, 8))

        self.dot = PulseDot(status, 34)
        self.dot.pack(side="left", padx=(14, 6), pady=10)

        txt = tk.Frame(status, bg=C_PANEL)
        txt.pack(side="left", fill="x", expand=True, pady=8)
        self.state_label = tk.Label(
            txt, text="● Gestoppt", bg=C_PANEL, fg=C_RED,
            font=("Segoe UI", 13, "bold"), anchor="w",
        )
        self.state_label.pack(fill="x")
        sub = tk.Frame(txt, bg=C_PANEL)
        sub.pack(fill="x")
        self.pid_label = tk.Label(
            sub, text="PID: –", bg=C_PANEL, fg=C_MUTED,
            font=("Segoe UI", 9), anchor="w",
        )
        self.pid_label.pack(side="left")
        self.uptime_label = tk.Label(
            sub, text="Läuft seit: –", bg=C_PANEL, fg=C_MUTED,
            font=("Segoe UI", 9), anchor="w",
        )
        self.uptime_label.pack(side="left", padx=(18, 0))

        self.progress = ttk.Progressbar(
            status, mode="indeterminate", length=150
        )
        self.progress.pack(side="right", padx=14)

        # -------- Steuerungs-Panel
        ctrl = tk.Frame(self, bg=C_SOFT)
        ctrl.pack(fill="x", padx=16, pady=(0, 8))

        self.btn_start = HoverButton(
            ctrl, text="▶  Start", base="#2ECC71", hover="#27AE60",
            fg="#FFFFFF", font=("Segoe UI", 10, "bold"),
            command=self.action_start,
        )
        self.btn_start.pack(side="left", padx=(12, 6), pady=10)

        self.btn_stop = HoverButton(
            ctrl, text="⏸  Stop", base=C_RED, hover="#C0392B",
            fg="#FFFFFF", font=("Segoe UI", 10, "bold"),
            command=self.action_stop,
        )
        self.btn_stop.pack(side="left", padx=6, pady=10)

        self.btn_restart = HoverButton(
            ctrl, text="↻  Restart", base=C_DARK, hover="#2E86C1",
            fg="#FFFFFF", font=("Segoe UI", 10, "bold"),
            command=self.action_restart,
        )
        self.btn_restart.pack(side="left", padx=6, pady=10)

        # Optionen rechts
        opts = tk.Frame(ctrl, bg=C_SOFT)
        opts.pack(side="right", padx=12, pady=6)
        tk.Checkbutton(
            opts, text="Auto-Restart", variable=self.auto_restart,
            bg=C_SOFT, fg=C_TEXT, activebackground=C_SOFT,
            selectcolor="#FFFFFF", font=("Segoe UI", 9),
        ).pack(side="right", padx=6)
        tk.Checkbutton(
            opts, text="Bot läuft nach Schließen weiter", variable=self.keep_running,
            bg=C_SOFT, fg=C_TEXT, activebackground=C_SOFT,
            selectcolor="#FFFFFF", font=("Segoe UI", 9),
        ).pack(side="right", padx=6)
        tk.Checkbutton(
            opts, text="Mit Windows starten", variable=self.autostart_var,
            command=self._toggle_autostart, bg=C_SOFT, fg=C_TEXT,
            activebackground=C_SOFT, selectcolor="#FFFFFF", font=("Segoe UI", 9),
        ).pack(side="right", padx=6)

        # -------- Dateien-Panel
        files = tk.Frame(self, bg=C_PANEL)
        files.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(
            files, text="  Dateien & Daten  ", bg=C_PANEL, fg=C_DARK,
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(10, 4), pady=8)
        for text, path in (
            ("📂 Projekt", BASE_DIR),
            ("📂 Logs", BASE_DIR / "logs"),
            ("📂 Daten (DB)", DATA_DIR),
            ("📂 Transkripte", TRANSCRIPT_DIR),
        ):
            HoverButton(
                files, text=text, base=C_MAIN, hover=C_DARK, fg="#FFFFFF",
                font=("Segoe UI", 9), padx=10, pady=5,
                command=lambda p=path: self._open(p),
            ).pack(side="left", padx=4, pady=8)
        HoverButton(
            files, text="🗑 Leeren", base="#EAF4FB", hover="#D6ECF9",
            fg=C_TEXT, font=("Segoe UI", 9), padx=10, pady=5,
            command=self._clear_console,
        ).pack(side="right", padx=(4, 10), pady=8)
        if PACK_BAT.exists():
            HoverButton(
                files, text="📦 ZIP bauen", base=C_LIGHT, hover=C_MAIN,
                fg=C_TEXT, font=("Segoe UI", 9), padx=10, pady=5,
                command=self.action_pack,
            ).pack(side="right", padx=4, pady=8)

        # -------- Konsole
        cons = tk.Frame(self, bg=C_CONSOLE_BG)
        cons.pack(fill="both", expand=True, padx=16, pady=(0, 6))
        bar = tk.Frame(cons, bg="#16283D")
        bar.pack(fill="x")
        tk.Label(
            bar, text="  ▸ Live-Konsole", bg="#16283D", fg=C_MAIN,
            font=("Consolas", 10, "bold"),
        ).pack(side="left")
        tk.Label(
            bar, text="PrimeFFA-Bot-Log   ", bg="#16283D", fg="#6C8AA5",
            font=("Consolas", 9),
        ).pack(side="right")
        self.console = tk.Text(
            cons, bg=C_CONSOLE_BG, fg=C_CONSOLE_FG, insertbackground=C_LIGHT,
            relief="flat", font=("Consolas", 10), state="disabled",
            wrap="word", padx=10, pady=8, bd=0,
            highlightthickness=0,
        )
        scroll = ttk.Scrollbar(cons, command=self.console.yview)
        self.console.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.console.pack(fill="both", expand=True)
        self.console.tag_config("err", foreground="#FF9B9B")
        self.console.tag_config("warn", foreground="#FFE08A")
        self.console.tag_config("info", foreground=C_LIGHT)
        self.console.tag_config("me", foreground="#8FE9FF")

        # -------- Fußzeile
        foot = tk.Frame(self, bg=C_SOFT)
        foot.pack(fill="x", padx=16, pady=(0, 12))
        self.size_label = tk.Label(
            foot, text="Daten werden geladen ...", bg=C_SOFT, fg=C_MUTED,
            font=("Segoe UI", 9),
        )
        self.size_label.pack(side="left", padx=12, pady=7)
        tk.Label(
            foot, text="Doppelklick auf start-hosting.bat startet diese Konsole",
            bg=C_SOFT, fg=C_MUTED, font=("Segoe UI", 9),
        ).pack(side="right", padx=12, pady=7)

        self._update_sizes()

    # -------------------------------------------------------- Ordner/Größen
    def _open(self, p: Path) -> None:
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
        open_path(p)
        self._log(f"[Konsole] Ordner geöffnet: {p}")

    def _clear_console(self) -> None:
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    def _update_sizes(self) -> None:
        parts = []
        for label, p in (("primeffa.db", DB_FILE), ("bot.log", LOG_FILE),
                         ("transcripts", TRANSCRIPT_DIR)):
            if p.exists():
                parts.append(f"{label}: {human_size(path_size(p))}")
            else:
                parts.append(f"{label}: –")
        count = sum(1 for _ in TRANSCRIPT_DIR.glob("*")) if TRANSCRIPT_DIR.exists() else 0
        self.size_label.config(text="   ·   ".join(parts) + f"   ·   {count} Transkripte")
        self.after(5000, self._update_sizes)

    # ------------------------------------------------------------ Logging
    def _log(self, text: str) -> None:
        self.q.put(("log", text))

    def _append(self, line: str) -> None:
        if not line.strip():
            return
        tag = ()
        if "ERROR" in line or "Traceback" in line:
            tag = ("err",)
        elif "WARNING" in line:
            tag = ("warn",)
        elif line.startswith("[Konsole]"):
            tag = ("me",)
        elif "INFO" in line:
            tag = ("info",)
        self.console.configure(state="normal")
        self.console.insert("end", line.rstrip("\n") + "\n", tag)
        # Zeilen begrenzen
        count = int(self.console.index("end-1c").split(".")[0])
        if count > 4000:
            self.console.delete("1.0", f"{count - 4000}.0")
        self.console.see("end")
        self.console.configure(state="disabled")

    # -------------------------------------------------------- Worker-Threads
    def _status_worker(self) -> None:
        while not self.stop_workers.is_set():
            pids = find_bot_processes()
            self.q.put(("status", pids))
            self.stop_workers.wait(2.0)

    def _tail_worker(self) -> None:
        while not self.stop_workers.is_set():
            try:
                if LOG_FILE.exists():
                    size = LOG_FILE.stat().st_size
                    if self.tail_pos is None or size < self.tail_pos:
                        self.tail_pos = size  # nur neue Zeilen ab jetzt
                    if size > self.tail_pos:
                        with open(LOG_FILE, "r", encoding="utf-8",
                                  errors="replace") as f:
                            f.seek(self.tail_pos)
                            data = f.read()
                            self.tail_pos = f.tell()
                        for line in data.splitlines():
                            if line.strip():
                                self.q.put(("log", line))
            except OSError:
                pass
            self.stop_workers.wait(0.5)

    # ------------------------------------------------------- GUI-Verarbeitung
    def _drain(self) -> None:
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._append(str(payload))
                elif kind == "status":
                    self._apply_status(payload)
                elif kind == "busy":
                    self._set_busy(bool(payload))
        except queue.Empty:
            pass
        self.after(250, self._drain)

    def _apply_status(self, pids: list[int]) -> None:
        self.known_pids = pids
        running = bool(pids)

        if running:
            if self.since is None:
                self.since = time.time()
                self.last_ok_since = time.time()
                self.restart_attempts = 0
                self.dot.pulse()
                own = self.proc_pid in pids if self.proc_pid else False
                self._log(
                    "[Konsole] Bot läuft"
                    + (f" (PID {self.proc_pid})." if own else
                       f" – übernommen (PID {', '.join(map(str, pids))}).")
                )
            self.state_label.config(text="● Läuft", fg="#2ECC71")
            self.dot.set_state("running")
            self.pid_label.config(text=f"PID: {', '.join(map(str, pids))}")
        else:
            had = self.since is not None
            self.since = None
            self.state_label.config(text="● Gestoppt", fg=C_RED)
            self.dot.set_state("stopped")
            self.pid_label.config(text="PID: –")
            if had and not self.busy:
                if self.manual_off or STOP_FLAG.exists():
                    pass   # manuell gestoppt – bleibt aus bis Start/Restart
                elif self.auto_restart.get():
                    self.restart_attempts += 1
                    self._log(
                        f"[Konsole] Bot ist weg – Auto-Restart "
                        f"(Versuch {self.restart_attempts}) in 3 s ..."
                    )
                    self.after(3000, self._auto_restart)
                else:
                    self._log("[Konsole] Bot gestoppt (Auto-Restart ist deaktiviert).")

    def _auto_restart(self) -> None:
        if (self.auto_restart.get() and not find_bot_processes()
                and not STOP_FLAG.exists() and not self.manual_off):
            self.action_start()

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.btn_start, self.btn_stop, self.btn_restart):
            b.config(state=state)
        if busy:
            self.progress.start(12)
            self.dot.set_state("starting")
            self.state_label.config(text="● Startet ...", fg="#E6A700")
        else:
            self.progress.stop()

    def _tick_ui(self) -> None:
        if self.since:
            secs = int(time.time() - self.since)
            h, rem = divmod(secs, 3600)
            m, s = divmod(rem, 60)
            self.uptime_label.config(text=f"Läuft seit: {h:02d}:{m:02d}:{s:02d}")
        else:
            self.uptime_label.config(text="Läuft seit: –")
        self.after(1000, self._tick_ui)

    # ------------------------------------------------------------ Aktionen
    def action_start(self) -> None:
        if self.busy:
            return
        self.manual_off = False
        mark_manually_stopped(False)
        self._set_busy(True)
        self.tail_pos = None
        threading.Thread(target=self._do_start, daemon=True).start()

    def _do_start(self) -> None:
        pids = find_bot_processes()
        if pids:
            self.proc_pid = pids[0]
            self.q.put(("log", "[Konsole] Bot läuft bereits – keine Doppelstart."))
            self.q.put(("busy", False))
            return
        self.q.put(("log", "[Konsole] Starte PrimeFFA-Bot ..."))
        pid = start_bot_process()
        if pid is None:
            self.q.put(("log", "[Konsole] FEHLER: Bot konnte nicht gestartet werden."))
        else:
            self.proc_pid = pid
            self.q.put(("log", f"[Konsole] Bot-Prozess gestartet (PID {pid})."))
        self.q.put(("busy", False))

    def action_stop(self) -> None:
        if self.busy:
            return
        self.manual_off = True
        mark_manually_stopped(True)
        self._set_busy(True)
        threading.Thread(target=self._do_stop, daemon=True).start()

    def _do_stop(self) -> None:
        pids = find_bot_processes()
        if not pids:
            self.q.put(("log", "[Konsole] Bot läuft nicht – bleibt gestoppt."))
            self.q.put(("busy", False))
            return
        self.q.put(("log", f"[Konsole] Stoppe PID {', '.join(map(str, pids))} sauber ..."))
        clean, left = stop_bot_processes(grace=8.0)
        if left:
            self.q.put(("log", f"[Konsole] FEHLER: Prozesse liefen weiter: {left}"))
        elif clean:
            self.q.put(("log", "[Konsole] Bot gestoppt – Discord-Verbindung sauber getrennt."))
        else:
            self.q.put(("log", "[Konsole] Bot hart beendet (sauberer Timeout)."))
        self.proc_pid = None
        self.q.put(("busy", False))

    def action_restart(self) -> None:
        if self.busy:
            return
        self.manual_off = False
        mark_manually_stopped(False)
        self._set_busy(True)
        self.tail_pos = None
        threading.Thread(target=self._do_restart, daemon=True).start()

    def _do_restart(self) -> None:
        pids = find_bot_processes()
        if pids:
            self.q.put(("log", "[Konsole] Restart: stoppe alten Prozess sauber ..."))
            stop_bot_processes(grace=6.0)
            for _ in range(10):
                if not find_bot_processes():
                    break
                time.sleep(0.4)
        self.q.put(("log", "[Konsole] Restart: starte neu ..."))
        pid = start_bot_process()
        if pid is None:
            self.q.put(("log", "[Konsole] FEHLER: Neustart fehlgeschlagen."))
        else:
            self.proc_pid = pid
            self.q.put(("log", f"[Konsole] Neugestartet (PID {pid})."))
        self.q.put(("busy", False))

    def action_pack(self) -> None:
        if self.busy:
            return
        self._set_busy(True)

        def run() -> None:
            try:
                out = subprocess.run(
                    ["cmd", "/c", str(PACK_BAT)],
                    cwd=str(BASE_DIR), capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    creationflags=CREATE_NO_WINDOW, timeout=180,
                )
                for line in (out.stdout or "").splitlines():
                    if line.strip():
                        self.q.put(("log", f"[ZIP] {line}"))
                if out.returncode != 0 and out.stderr:
                    for line in (out.stderr.splitlines())[:10]:
                        self.q.put(("log", f"[ZIP] {line}"))
                else:
                    self.q.put(("log", "[Konsole] ZIP fertig gebaut."))
            except Exception as exc:
                self.q.put(("log", f"[Konsole] ZIP-Fehler: {exc}"))
            self.q.put(("busy", False))

        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------- Autostart/Schließen
    def _toggle_autostart(self) -> None:
        try:
            autostart_set(self.autostart_var.get())
            state = "aktiviert" if self.autostart_var.get() else "deaktiviert"
            self._log(f"[Konsole] Windows-Autostart {state}.")
        except OSError as exc:
            self.autostart_var.set(False)
            self._log(f"[Konsole] Autostart fehlgeschlagen: {exc}")

    def on_close(self) -> None:
        if self.keep_running.get():
            if self.known_pids:
                self._log(
                    "[Konsole] Konsole geschlossen – der Bot läuft weiter "
                    f"(PID {', '.join(map(str, self.known_pids))})."
                )
            self.stop_workers.set()
            self.destroy()
            return
        if messagebox.askyesno(
            "Konsole schließen",
            "Bot stoppen und die Konsole schließen?\n\n"
            "Ja = Bot wird beendet.\n"
            "Nein = Konsole schließt, der Bot läuft weiter.",
            parent=self,
        ):
            self.stop_workers.set()
            pids = find_bot_processes()
            if pids:
                kill_processes(pids)
            self.destroy()
        # sonst: Konsole bleibt offen


# =============================================================== Einstieg
def selftest() -> int:
    print("BASE_DIR   :", BASE_DIR)
    print("bot.py     :", "OK" if BOT_SCRIPT.exists() else "FEHLT")
    print("Python     :", PYTHON)
    print("Autostart  :", "aktiv" if autostart_get() else "inaktiv")
    print("tkinter    :", "OK" if HAS_TK else "fehlt (GUI nur lokal)")
    pids = find_bot_processes()
    print("Bot-Prozess:", pids if pids else "keiner")
    print("DB         :", DB_FILE if DB_FILE.exists() else "noch nicht angelegt")
    print("logs/bot.log:", LOG_FILE if LOG_FILE.exists() else "noch nicht angelegt")
    ok = BOT_SCRIPT.exists() and PYTHON.endswith((".exe", "python", "python3"))
    print("SELFTEST", "OK" if ok else "FEHLER")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    smoke = "--smoke" in sys.argv
    app = HostingApp(auto_boot=not smoke)
    if smoke:
        app.after(1500, app.destroy)
        app.after(1600, lambda: print("SMOKE OK"))
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
