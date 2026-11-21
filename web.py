#!/usr/bin/env python3
"""PrimeFFA Web-Konsole – die Hosting-Konsole im Browser, mit Login.

- Login Pflicht bei JEDEM Seitenaufruf (auch nach Reload/Neustart)
- Benutzername: JoeloKocht
- Falsch  -> "Falsches Passwort oder Benutzername"
- Richtig -> Konsole mit nur Start / Stop / Restart, Status + Live-Logs

Cloud-tauglich:
- HOST/PORT kommen aus der Umgebung (HOST=0.0.0.0, PORT z. B. 8765)
- plattformunabhängige Prozesssteuerung (siehe hosting.py)
- keine Windows-only Features (Autostart/Ordner öffnen werden ignoriert)

Start:  python web.py            (öffnet lokal automatisch den Browser)
        python web.py --no-browser
Test:   python web.py --selftest
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import hosting as H

WEB_USER = "JoeloKocht"
WEB_PASS = "JoelNass2014"
# Cloud-Hosts setzen PORT (und oft HOST); lokal gilt 127.0.0.1:8765.
HOST = os.environ.get("HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
PORT = int(os.environ.get("PORT", "8765"))

BASE_DIR = H.BASE_DIR
HTML_FILE = BASE_DIR / "webapp.html"
CFG_FILE = BASE_DIR / "data" / "web_config.json"
STOP_REQUEST = BASE_DIR / "data" / "shutdown.request"   # bot.py räumt sie selbst auf
STOP_FLAG = BASE_DIR / "data" / "bot.stopped"           # "manuell gestoppt" (geteilt)

MAX_LOGIN_FAILURES = 5
LOGIN_LOCK_SECONDS = 30

_state_lock = threading.Lock()
_state: dict = {
    "tokens": set(),
    "since": None,            # Epoch-Sekunden, wenn der Bot läuft
    "manual_off": False,      # User hat Stop gedrückt → Wachhund bleibt ruhig
    "attempts": 0,            # Auto-Restart-Versuche (Zähler für Anzeige)
    "last_start_try": 0.0,    # letzter Startversuch des Wachhunds
    "failures": 0,            # fehlgeschlagene Logins
    "locked_until": 0.0,
    "cfg": {"auto_restart": True, "keep_running": True, "autostart": False},
}

AUTOSTART_NAME = "PrimeFFA-Web"


# ------------------------------------------------------------ Konfiguration
def _find_pythonw() -> str:
    return H.find_pythonw()


def autostart_get() -> bool:
    return H.autostart_get_named(AUTOSTART_NAME)


def autostart_set(on: bool) -> None:
    """Web-Konsole (web.py) mit Windows starten – eigener Registry-Eintrag."""
    H.autostart_set_named(
        AUTOSTART_NAME,
        on,
        script=str(Path(__file__).resolve()),
    )


def load_cfg() -> None:
    try:
        if CFG_FILE.exists():
            data = json.loads(CFG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _state["cfg"].update({k: bool(v) for k, v in data.items()
                                      if k in _state["cfg"]})
    except Exception:
        pass
    # Autostart-Status vom System holen (Quelle der Wahrheit = Registry)
    try:
        _state["cfg"]["autostart"] = autostart_get()
    except Exception:
        pass


def save_cfg() -> None:
    try:
        CFG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CFG_FILE.write_text(
            json.dumps(_state["cfg"], indent=2), encoding="utf-8"
        )
    except Exception:
        pass


# ------------------------------------------------------------- Status-Logik
def current_pids() -> list[int]:
    return H.find_bot_processes()


def status_payload() -> dict:
    with _state_lock:
        pids = current_pids()
        running = bool(pids)
        if running and _state["since"] is None:
            _state["since"] = time.time()
            _state["attempts"] = 0
        elif not running:
            _state["since"] = None
        return {
            "running": running,
            "pids": pids,
            "since": _state["since"],
            "manual_off": _state["manual_off"],
            "auto_restart": _state["cfg"]["auto_restart"],
            "keep_running": _state["cfg"]["keep_running"],
            "autostart": _state["cfg"]["autostart"],
            "attempts": _state["attempts"],
        }


def do_start() -> str:
    with _state_lock:
        _state["manual_off"] = False      # Start = Wachhund übernimmt wieder
        for f in (STOP_FLAG, STOP_REQUEST):
            try:
                f.unlink()
            except OSError:
                pass
        pids = current_pids()
        if pids:
            return f"Bot läuft bereits (PID {', '.join(map(str, pids))})."
        pid = H.start_bot_process()
        if pid is None:
            return "FEHLER: Bot konnte nicht gestartet werden."
        return f"Bot gestartet (PID {pid})."


def do_stop() -> str:
    with _state_lock:
        _state["manual_off"] = True       # Stop = bleibt aus, bis Start
        # Geteiltes Stopp-Flag: alle Konsole/Wachhunde respektieren das
        try:
            STOP_FLAG.parent.mkdir(parents=True, exist_ok=True)
            STOP_FLAG.write_text("stopped", encoding="utf-8")
        except OSError:
            pass
        pids = current_pids()
        if not pids:
            return "Bot läuft nicht – bleibt gestoppt."

        # 1) Sauberen Shutdown anfordern (bot.py meldet sich bei Discord ab)
        try:
            STOP_REQUEST.write_text("stop", encoding="utf-8")
        except OSError:
            pass
        graceful = True
        for _ in range(20):               # max. 8 s warten
            if not current_pids():
                break
            time.sleep(0.4)
        else:
            graceful = False

        # 2) Falls er noch läuft: hart beenden
        left = current_pids()
        if left:
            H.kill_processes(left)
            for _ in range(15):
                if not current_pids():
                    break
                time.sleep(0.4)
        try:
            STOP_REQUEST.unlink()
        except OSError:
            pass
        left = current_pids()
        if left:
            return f"FEHLER: Prozesse liefen weiter: {left}"
        how = "sauber getrennt" if graceful else "hart beendet"
        return f"Bot gestoppt ({how}, PID {', '.join(map(str, pids))})."


def do_restart() -> str:
    with _state_lock:
        _state["manual_off"] = False      # Restart = wieder an
        for f in (STOP_FLAG, STOP_REQUEST):
            try:
                f.unlink()
            except OSError:
                pass
        pids = current_pids()
        if pids:
            # sauber bitten, sonst hart – wie beim Stop
            try:
                STOP_REQUEST.write_text("stop", encoding="utf-8")
            except OSError:
                pass
            for _ in range(15):
                if not current_pids():
                    break
                time.sleep(0.4)
            left = current_pids()
            if left:
                H.kill_processes(left)
                for _ in range(15):
                    if not current_pids():
                        break
                    time.sleep(0.4)
            try:
                STOP_REQUEST.unlink()
            except OSError:
                pass
        pid = H.start_bot_process()
        if pid is None:
            return "FEHLER: Neustart fehlgeschlagen."
        return f"Neugestartet (PID {pid})."


# ---------------------------------------------------------- Wachhund
def watchdog_worker() -> None:
    """Hält den Bot IMMER am Laufen.

    Regeln:
    - Bot tot und nicht manuell gestoppt -> sofort neu starten (unbegrenzt).
    - User hat Stop gedrückt (Speicher ODER shared Flag-Datei) -> ruhig bis Start.
    - Kein Versuchs-Limit, keine Abschaltung: solange der PC an ist, läuft er.
    """
    while True:
        time.sleep(2.0)
        try:
            with _state_lock:
                if _state["manual_off"] or STOP_FLAG.exists():
                    continue
                if not _state["cfg"]["auto_restart"]:
                    continue
                pids = current_pids()
                if pids:
                    _state["attempts"] = 0
                    continue
                # Rate-Limit: max. 1 Startversuch alle 2 s
                now = time.time()
                if now - _state["last_start_try"] < 2.0:
                    continue
                _state["last_start_try"] = now
                _state["attempts"] += 1
                H.start_bot_process()
        except Exception:
            pass


# ------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "PrimeFFA/1.0"

    # ------------------------------------------------------------- Hilfen
    def log_message(self, fmt: str, *args) -> None:  # still
        pass

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text: str) -> None:
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8") or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _authed(self) -> bool:
        header = self.headers.get("Authorization") or ""
        if not header.startswith("Bearer "):
            return False
        token = header[7:].strip()
        with _state_lock:
            return token in _state["tokens"]

    def _require_auth(self) -> bool:
        if self._authed():
            return True
        self._json(401, {"ok": False, "error": "Nicht eingeloggt."})
        return False

    # -------------------------------------------------------------- GET
    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        path = url.path

        if path == "/":
            # Jeder Seitenaufruf verwirft alle Sitzungen -> IMMER neu einloggen
            with _state_lock:
                _state["tokens"].clear()
            if HTML_FILE.exists():
                self._html(HTML_FILE.read_text(encoding="utf-8"))
            else:
                self._html("<h1>webapp.html fehlt</h1>")
            return

        if path == "/api/status":
            if not self._require_auth():
                return
            self._json(200, {"ok": True, **status_payload()})
            return

        if path == "/api/logs":
            if not self._require_auth():
                return
            qs = parse_qs(url.query)
            try:
                offset = int(qs.get("offset", ["0"])[0])
            except ValueError:
                offset = 0
            self._json(200, read_logs(offset))
            return

        if path == "/api/files":
            if not self._require_auth():
                return
            files = []
            for name, p in (
                ("data/primeffa.db", H.DB_FILE),
                ("logs/bot.log", H.LOG_FILE),
                ("logs/hosting.log", BASE_DIR / "logs" / "hosting.log"),
            ):
                files.append({
                    "name": name,
                    "size": H.path_size(p) if p.exists() else None,
                    "exists": p.exists(),
                })
            tr = 0
            if H.TRANSCRIPT_DIR.exists():
                tr = sum(1 for _ in H.TRANSCRIPT_DIR.glob("*"))
            self._json(200, {"ok": True, "files": files, "transcripts": tr})
            return

        self._json(404, {"ok": False, "error": "Unbekannter Pfad."})

    # ------------------------------------------------------------- POST
    def do_POST(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        path = url.path
        data = self._body()

        if path == "/api/login":
            self.handle_login(data)
            return

        if not self._require_auth():
            return

        if path == "/api/logout":
            header = self.headers.get("Authorization") or ""
            token = header[7:].strip() if header.startswith("Bearer ") else ""
            with _state_lock:
                _state["tokens"].discard(token)
            self._json(200, {"ok": True})
            return

        if path == "/api/start":
            self._json(200, {"ok": True, "message": do_start()})
            return

        if path == "/api/stop":
            self._json(200, {"ok": True, "message": do_stop()})
            return

        if path == "/api/restart":
            self._json(200, {"ok": True, "message": do_restart()})
            return

        if path == "/api/config":
            with _state_lock:
                for key in ("auto_restart", "keep_running", "autostart"):
                    if key in data:
                        _state["cfg"][key] = bool(data[key])
                autostart = _state["cfg"]["autostart"]
            if "autostart" in data and os.name == "nt":
                # Windows-Autostart – auf Servern/Cloud ohne Registry ein No-Op
                try:
                    autostart_set(autostart)
                except OSError as exc:
                    with _state_lock:
                        _state["cfg"]["autostart"] = autostart_get()
                    self._json(500, {"ok": False, "error": f"Autostart: {exc}"})
                    return
            save_cfg()
            self._json(200, {"ok": True, **status_payload()})
            return

        self._json(404, {"ok": False, "error": "Unbekannter Pfad."})

    # ------------------------------------------------------------ Login
    def handle_login(self, data: dict) -> None:
        user = str(data.get("user", ""))
        pw = str(data.get("pass", ""))
        now = time.time()

        with _state_lock:
            if now < _state["locked_until"]:
                wait = int(_state["locked_until"] - now)
                self._json(
                    429,
                    {"ok": False,
                     "error": f"Zu viele Versuche – bitte {wait} Sekunden warten."},
                )
                return

            user_ok = hmac.compare_digest(user.encode(), WEB_USER.encode())
            pass_ok = hmac.compare_digest(pw.encode(), WEB_PASS.encode())

            if user_ok and pass_ok:
                token = secrets.token_urlsafe(32)
                _state["tokens"].add(token)
                _state["failures"] = 0
                _state["since"] = _state["since"] if current_pids() else None
                self._json(200, {"ok": True, "token": token})
                return

            _state["failures"] += 1
            if _state["failures"] >= MAX_LOGIN_FAILURES:
                _state["failures"] = 0
                _state["locked_until"] = now + LOGIN_LOCK_SECONDS
            self._json(
                401, {"ok": False, "error": "Falsches Passwort oder Benutzername"}
            )


# ------------------------------------------------------------ Logs lesen
def read_logs(offset: int) -> dict:
    path = H.LOG_FILE
    try:
        if not path.exists():
            return {"ok": True, "offset": 0, "lines": []}
        size = path.stat().st_size
        if size < offset:
            offset = 0
        lines: list[str] = []
        if size > offset:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(offset)
                data = f.read()
                offset = f.tell()
            lines = [ln for ln in data.splitlines() if ln.strip()]
        return {"ok": True, "offset": offset, "lines": lines[-200:]}
    except OSError:
        return {"ok": True, "offset": offset, "lines": []}


# ------------------------------------------------------------------ Start
def selftest() -> int:
    print("HTML      :", "OK" if HTML_FILE.exists() else "FEHLT (webapp.html)")
    print("Port      :", f"{HOST}:{PORT}")
    print("Login     :", WEB_USER)
    print("Bot       :", current_pids() or "gestoppt")
    print("Autostart :", _state["cfg"]["autostart"])
    print("SELFTEST", "OK" if HTML_FILE.exists() else "FEHLER")
    return 0 if HTML_FILE.exists() else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    first_run = not CFG_FILE.exists()
    load_cfg()

    # PC-Neustart/Konsole-Neustart: Stopp-Flag löschen -> Bot kommt wieder hoch
    for f in (STOP_FLAG, STOP_REQUEST):
        try:
            f.unlink()
        except OSError:
            pass
    _state["manual_off"] = False

    # "PC an = Bot an": Web-Konsole startet mit Windows (beim ersten Start aktivieren)
    # – nur lokal unter Windows; auf dem Server übernimmt der Host-Start.
    if os.name == "nt":
        try:
            if first_run:
                _state["cfg"]["autostart"] = True
            if _state["cfg"]["autostart"]:
                autostart_set(True)
            else:
                autostart_set(False)
        except OSError:
            pass

    save_cfg()
    threading.Thread(target=watchdog_worker, daemon=True).start()

    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        # läuft schon → zweite Instanz nicht starten
        print(f"Port {PORT} belegt – Web-Konsole läuft bereits.")
        return 0

    # Anzeige-URL: 0.0.0.0 -> im Browser 127.0.0.1 nutzen
    show_host = "127.0.0.1" if HOST in ("0.0.0.0", "::", "") else HOST
    print(f"PrimeFFA Web-Konsole: http://{show_host}:{PORT}")

    # Browser nur lokal öffnen (auf Servern/Cloud läuft es als Dienst)
    if "--no-browser" not in sys.argv and sys.stdout.isatty():
        threading.Timer(
            1.2, lambda: webbrowser.open(f"http://{show_host}:{PORT}")
        ).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nWeb-Konsole beendet.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
