# 🩵 PrimeFFA Bot – Installations-, Einrichtungs- & Hosting-Anleitung

Schritt für Schritt: vom leeren PC bis zum Bot, der **24/7 läuft**.

---

## Teil 1 – Voraussetzungen

1. **Python 3.11 oder neuer**
   - Download: <https://www.python.org/downloads/>
   - Installer starten → **Häkchen bei "Add python.exe to PATH"** → Installieren
   - Prüfen: `Win + R` → `cmd` → `python --version` (muss 3.11+ zeigen)
2. **Ein Discord-Account** mit Admin-Rechten auf deinem Server *PrimeFFA*

---

## Teil 2 – Discord Bot anlegen (2 Minuten)

1. Öffne <https://discord.com/developers/applications> → **New Application**
   - Name z. B. `PrimeFFA` → **Create**
2. Links **Bot** → **Reset Token** → Token kopieren (nur du siehst ihn!)
   - ⚠️ Niemals irgendwohin posten – er gehört nur in die `.env`
3. Gleich unterhalb **Privileged Gateway Intents** aktivieren:
   - ✅ **SERVER MEMBERS INTENT** (nötig für Willkommen/Verlassen/Tickets)
   - ✅ **MESSAGE CONTENT INTENT** (nötig für das Counting-System)
   - (Presence Intent optional)
4. Links **OAuth2 → URL Generator**:
   - **Scopes:** `bot` + `applications.commands`
   - **Bot Permissions:** `View Channels`, `Send Messages`, `Embed Links`,
     `Attach Files`, `Read Message History`, `Manage Channels`,
     `Manage Roles`, `Manage Messages`, `Mention Everyone`
   - URL unten kopieren → im Browser öffnen → Server auswählen → **Autorisieren**
     (dazu brauchst du Admin-Rechte)

---

## Teil 3 – Bot lokal installieren & starten

Ordner: `C:\Users\Joel\Downloads\PrimeFFA-Bot`

### 3.1 Token eintragen

Öffne die Datei **`.env`** mit dem Editor (Rechtsklick → Öffnen mit → Editor):

```env
DISCORD_TOKEN=HIER_DEINEN_TOKEN_EINTRAGEN
TEST_GUILD_ID=HIER_DEINE_SERVER_ID_EINTRAGEN
```

- **Token:** aus Teil 2, Schritt 2
- **TEST_GUILD_ID:** Rechtsklick auf deinen Server → *Server-ID kopieren*
  (Developer-Modus aktivieren: Einstellungen → Erweitert → Entwicklermodus)
  → sorgt dafür, dass die Commands **sofort** erscheinen (statt nach bis zu 1 Std.)

### 3.2 Abhängigkeiten + Start

**Option A – Doppelklick (einfach):** `start.bat`
(startet den Bot und startet ihn bei Absturz automatisch neu)

**Option B – Terminal:**

```bat
cd C:\Users\Joel\Downloads\PrimeFFA-Bot
python -m pip install -r requirements.txt
python bot.py
```

Erfolgreich sieht du so etwas:

```
INFO | primeffa | Cog geladen: cogs.admin
INFO | primeffa | 28 Slash-Commands synchronisiert.
INFO | primeffa | Eingeloggt als PrimeFFA (ID: ...)
INFO | primeffa | Eingeloggt als ... | 1 Server
```

> Tipp: Damit der Bot auch im Hintergrund weiterläuft, kannst du einfach
> `start.bat` doppelt ausführen oder den Bot auf einem Hoster betreiben
> (siehe Teil 5 – das ist der richtige Weg für "immer an").

---

## Teil 4 – Einrichtung im Server

| Reihenfolge | Befehl | Was er macht |
|---|---|---|
| 1 | `/setup` | Zeigt den Status aller Systeme |
| 2 | `/ticket-setup staff_role:@Team log_channel:#logs panel_channel:#support` | Legt das **Ticket-Panel** mit Dropdown ins Panel-Channel |
| 3 | `/ticket-roles category:🛠️ Support role:@Support` | Eigene Support-Rolle pro Kategorie (wiederholen für jede Kategorie) |
| 4 | `/ticket-logs channel:#ticket-logs` | Ticket-Logs (Erstellung, Claim, Close, Transkript) |
| 5 | `/welcome-setup channel:#willkommen` | Willkommens-Embed (optional `message:` eigene Textvorlage) |
| 6 | `/leave-setup channel:#verlassen` | Verlassen-Embed |
| 7 | `/giveaway prize:Nitro duration:1h winners:2 channel:#giveaways` | Giveaway starten |
| 8 | `/counting-setup channel:#zahlen` | Counting-Channel |
| 9 | `/voice-ping-setup voice_channel:🔊 TeamSpeak text_channel:#voice-ping role1:@Gamer role2:@VIP cooldown:60` | Voice-Rang-Ping |

Weitere Befehle: `/config` (alle Einstellungen), `/bot-info`,
`/ticket-stats`, `/ticket-closed number:12`, `/counting-record`,
`/voice-ping-status`, `/ticket-claim`, `/ticket-close`, `/ticket-reopen`,
`/ticket-add`, `/ticket-remove`, `/ticket-transcript`,
`/giveaway-end`, `/giveaway-reroll`, `/giveaway-cancel`.

### Ticket-Buttons im Ticket

`🙋 Beanspruchen` · `➕ Hinzufügen` · `➖ Entfernen` · `🔁 Übertragen` ·
`📄 Transkript` · `🔒 Schließen` · `🔓 Öffnen` · `🗑️ Löschen` (mit Bestätigung)

Alle Buttons funktionieren auch nach einem Neustart des Bot (persistente Views).

---

## Teil 5 – Hosting: Bot 24/7 / immer an (kostenlos)

Ein Bot auf deinem PC läuft nur, solange der PC an ist. Für **immer an**
brauchst du einen Hoster. Hier die passenden kostenlosen Optionen, sortiert
nach "wie zuverlässig läuft er wirklich 24/7":

### Option 0 – Cloud/Lokale Hosting-Konsole (sofort, gratis, Bot läuft auch ohne PC)

**Web-Konsole (empfohlen):** mit **`start-web.bat`** (oder `py web.py`)
– der Browser öffnet automatisch `http://127.0.0.1:8765`.

- **Login Pflicht bei jedem Seitenaufruf** (auch Reload/Neustart des Browsers):
  Benutzer `JoeloKocht`, Passwort `JoelNass2014`
- Falsche Daten: Meldung **„Falsches Passwort oder Benutzername"**
  (nach 5 Fehlversuchen 30 Sekunden Sperre), Passwort per 👁/Checkbox einblendbar
- Nach dem Login: **nur Start, Stop, Restart**, Status mit PID/Läufzeit
  (der Bot läuft 24/7 im Cloud-Hosting – auch wenn dein PC aus ist)
- **Wachhund (immer an):** Solange dein PC läuft, bleibt der Bot an –
  stirbt er (Absturz, Task-Manager, was auch immer), startet er in ~3 s
  von selbst wieder. **Stop** hält ihn gestoppt, bis du **Start** drückst.
- **Sauberes Stoppen:** Stop meldet den Bot ordnungsgemäß von Discord ab –
  er wird im Server sofort offline (kein „hängt noch als online" mehr).
- Windows-Autostart aktiv für die Konsole lokal (Registry `PrimeFFA-Web`)
- Einstellungen werden in `data/web_config.json` gespeichert.
- Der Web-Server läuft im Hintergrund weiter, auch wenn du den Browser schließt.

**Erklärung der Architektur:** `web.py` ist der Hosting-Prozess – er startet
den Bot (`bot.py`) als Kind-Prozess und beobachtet ihn. Auf einem Hoster
(Discloud, bot-hosting.net, foil.com, Samuel.tech) läuft `web.py` dort und deine
lokale Web-Konsole ist nur noch der Browser, der sich per HTTP an den Server
verbindet. `hosting.py` ist plattformunabhängig (Windows/Linux/macOS),
damit der Hoster-Server ein Linux im Grunde auch übernehmen kann.

**Desktop-Konsole (optional):** Doppelklick auf **`start-hosting.bat`** (oder `py hosting.py`)
– dieselben Funktionen als Tkinter-Fenster.

Die mitgelieferte **`hosting.py`** ist deine eigene kleine Hosting-Konsole.
Sie startet, stoppt und startet den Bot neu, zeigt alle Logs in Echtzeit und
holt den Bot nach einem PC-Neustart automatisch zurück.

**Starten:** Doppelklick auf **`start-hosting.bat`** (oder `py hosting.py`).

| Button / Option | Was es macht |
|---|---|
| ▶ **Start** | Startet den Bot (oder übernimmt ihn, wenn er schon läuft) |
| ⏸ **Stop** | Beendet den Bot-Prozess sauber |
| ↻ **Restart** | Stop + Start in einem Schritt |
| ☑ **Auto-Restart** | Startet den Bot nach einem Absturz automatisch neu |
| ☑ **Mit Windows starten** | Trägt die Konsole in den Windows-Autostart ein |
| ☑ **Bot läuft nach Schließen weiter** | Konsole zu, Bot bleibt an (Standard) |
| 📂 **Projekt / Logs / Daten / Transkripte** | Öffnet die Ordner mit allen Bot-Daten |
| 📦 **ZIP bauen** | Erstellt die Hosting-ZIP neu (`pack.bat`) |
| 🗑 **Leeren** | Leert die Live-Konsole |

- **Live-Konsole:** jeder Log-Eintrag des Bots erscheint sofort (Fehler in Rot,
  Warnungen in Gelb).
- **Status:** grüner pulsierender Punkt = läuft, mit PID und Laufzeit.
- **Daten bleiben:** SQLite-Datenbank (`data/primeffa.db`), Logs (`logs/`)
  und Transkripte (`transcripts/`) liegen direkt daneben und gehen nie verloren.
- **Hintergrund:** animierter Babyblauer Farbverlauf mit schwebenden Blasen.

Wichtig: Auf dem Cloud-Host läuft der Bot **immer** – egal ob dein PC aus ist.
Lokal läuft der Bot, solange **dein PC eingeschaltet** ist.

### Option A – Discloud (empfohlen, kostenlos & immer an)

Discloud ist speziell für Discord-Bots, läuft rund um die Uhr und ist kostenlos.

1. Account erstellen: <https://discloud.com>
2. ZIP erstellen: Doppelklick auf **`pack.bat`** → es entsteht `PrimeFFA-Bot.zip`
   (enthält `bot.py`, `cogs/`, `.env` mit Token, `discloud.config`)
3. Im Discloud-Dashboard: **Upload** → `PrimeFFA-Bot.zip` wählen → hochladen
4. Discloud erkennt automatisch `discloud.config` (`main=bot.py`) und installiert
   `requirements.txt` selbst
5. Der Bot startet sofort und bleibt an – auch wenn dein PC aus ist
6. Neustarts/Updates: einfach neues ZIP hochladen

> Wichtig: `discloud.config` liegt bereits im Ordner und ist auf `bot.py`
> eingestellt – nichts zu ändern.

### Option B – bot-hosting.net (kostenlos, immer an)

1. Account: <https://bot-hosting.net>
2. Neuen Server anlegen → Sprache **Python** → Plan (Free) wählen
3. Dateien hochladen: dasselbe ZIP aus `pack.bat` entpacken und alles hochladen
   (oder über den Dateimanager: `bot.py`, `cogs/`, `config.py`, `database.py`,
   `utils.py`, `requirements.txt`, `.env`, `discloud.config`)
4. Im Panel: **Startup-Command** = `python bot.py`
5. `requirements.txt` wird meist automatisch installiert, sonst manuell
   `pip install -r requirements.txt`
6. Starten → läuft 24/7

### Option C – Oracle Cloud Free Tier (der "garantiert immer an"-Weg)

Ein eigener Linux-Server, kostenlos für immer, kein Sleep, keine Limits.

1. Konto: <https://www.oracle.com/cloud/free/> (kreditkarte nötig, nichts wird abgebucht)
   → Instanz "Always Free" erstellen (Ubuntu 24.04, ARM oder AMD, 1 CPU/1 GB reicht)
2. Per SSH einloggen (Windows: `ssh ubuntu@DEINE_IP`)
3. Dateien hochladen (von deinem PC aus, im Projektordner):
   ```bat
   scp -r bot.py config.py database.py utils.py requirements.txt .env discloud.config cogs ubuntu@DEINE_IP:~/
   ```
4. Auf dem Server:
   ```bash
   sudo apt update && sudo apt install -y python3-pip python3-venv
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
5. Als **Dienst** einrichten (startet automatisch bei Boot & nach Absturz):
   ```bash
   sudo nano /etc/systemd/system/primeffa.service
   ```
   ```ini
   [Unit]
   Description=PrimeFFA Discord Bot
   After=network.target

   [Service]
   WorkingDirectory=/home/ubuntu
   ExecStart=/home/ubuntu/venv/bin/python bot.py
   Restart=always
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable primeffa
   sudo systemctl start primeffa
   sudo systemctl status primeffa     # "active (running)" = läuft
   journalctl -u primeffa -f          # Live-Logs
   ```
   → Der Bot läuft jetzt **garantiert immer**, startet sich selbst neu und
   startet mit dem Server.

### Option D – Sonstige (kurz)

| Hoster | Einschätzung |
|---|---|
| **Render.com Free** | Funktioniert, schläft aber nach ~15 Min. ohne Traffic → für Bots **nicht** "immer an" |
| **Railway / Replit** | Free-Guthaben/Starts begrenzt, Replit hat Sleep + Rate-Limits |
| **Cyclic, Zeabur, Fly.io** | Free-Pläne stark eingeschränkt/geändert → nicht zuverlässig |
| **Dein eigener PC** | Nur solange der PC an ist → `start.bat` als Autostart (Win+R → `shell:startup`) |

**Empfehlung:** Discloud oder bot-hosting.net für den schnellen kostenlosen Start,
Oracle VPS wenn es wirklich ohne Ausfälle laufen soll.

### Daten & Transkripte beim Hosting

- `data/primeffa.db` = alle Einstellungen, Tickets, Giveaways (überlebt Neustarts)
- `transcripts/` = gespeicherte Ticket-Transkripte (HTML, babyblau)
- Auf Free-Hostern kann der Speicher bei manchen Anbietern zurückgesetzt werden →
  deshalb regelmäßig `data/` + `transcripts/` herunterladen und sichern
  (auf Oracle VPS ist alles dauerhaft)

---

## Teil 6 – Häufige Probleme

| Problem | Lösung |
|---|---|
| `Improper token has been passed` | Token in `.env` ist falsch/Platzhalter → neu aus dem Developer Portal kopieren |
| Commands erscheinen nicht | `TEST_GUILD_ID` in `.env` eintragen + Bot neu starten; global können bis zu 1 Std. vergehen |
| Willkommen/Verlassen funktioniert nicht | **Server Members Intent** im Developer Portal aktivieren |
| Counting reagiert nicht | **Message Content Intent** aktivieren |
| `403 Forbidden` beim Ticket-Erstellen | Bot braucht `Manage Channels` + `Manage Roles`; Rolle des Bots muss **über** den Ticket-Rollen liegen |
| Rollen-Ping erscheint nicht | Bot braucht `Mention Everyone`-Rechte für Rollen-Mentions; Cooldown beachten |
| Bot stoppt beim Schließen des Terminals | `start.bat` nutzen oder auf Hoster (Teil 5) gehen |

---

## Teil 7 – Wartung & Updates

- **Logs:** `logs/bot.log`
- **Datenbank backup:** `data/primeffa.db` kopieren
- **Neue Version deployen:** Dateien ändern → `pack.bat` → ZIP hochladen → fertig
- **Testlauf ohne Token-Risiko:** `python test_load.py` (prüft alle Cogs/Views/Commands)
