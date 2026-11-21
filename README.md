# 🩵 PrimeFFA Bot – Baby Blue Edition

Vollständiger Discord-Bot für den **PrimeFFA**-Server im einheitlichen Baby-Blue-Design
(`#89CFF0` / `#BFEFFF` / `#5DADE2`).

## Enthaltene Systeme

| System | Befehle / Funktion |
|---|---|
| 🎫 Ticketsystem | Panel mit Dropdown (5 Kategorien), private Channels, Claim, Close/Reopen/Delete, Add/Remove/Transfert, Transkripte (HTML), Logs, Statistiken, Kategorie-Rollen, Anti-Doppel-Ticket |
| 👋 Willkommen | `/welcome-setup` (Embed mit Avatar + Mitgliederzahl) |
| 🚪 Verlassen | `/leave-setup` |
| 🎉 Giveaways | `/giveaway`, `/giveaway-end`, `/giveaway-reroll`, `/giveaway-cancel`, Teilnahme-Button, mehrere Gewinner, Neustart-sicher |
| 🔢 Counting | `/counting-setup`, `/counting-reset`, `/counting-record`, Rekord, Anti-Doppel-Zahl |
| 🔔 Voice-Ping | `/voice-ping-setup` (Voice-Channel → Rollen-Ping mit Cooldown) |
| ⚙️ Admin | `/setup`, `/config`, `/bot-info` + alle Permission-Checks |

**28 Slash-Commands gesamt.**

## Struktur

```
PrimeFFA-Bot/
├── bot.py            # Einstiegspunkt
├── config.py         # Farben & Branding (Babyblau)
├── database.py       # SQLite (alle Einstellungen überleben Neustarts)
├── utils.py          # Einheitliche Embeds
├── requirements.txt
├── .env              # DEIN TOKEN (nicht hochladen!)
├── discloud.config   # für Discloud-Upload
├── start.bat         # Windows: Start mit Auto-Restart
├── pack.bat          # ZIP für Hosting erstellen
├── ANLEITUNG.md      # Schritt-für-Schritt-Anleitung
├── cogs/
│   ├── admin.py      # /setup, /config, /bot-info
│   ├── welcome.py    # Willkommen + Verlassen
│   ├── tickets.py    # komplettes Ticketsystem
│   ├── giveaway.py   # Giveaway-System
│   ├── counting.py   # Counting-System
│   └── voiceping.py  # Voice-Rang-Ping
├── data/             # SQLite-Datenbank (wird automatisch angelegt)
├── transcripts/      # gespeicherte Ticket-Transkripte
└── logs/             # Bot-Logs
```

## Quick-Start

```bash
pip install -r requirements.txt
# Token in .env eintragen:
#   DISCORD_TOKEN=dein_token
python bot.py
```

Details: **[ANLEITUNG.md](ANLEITUNG.md)**

## Wichtige Hinweise

- Im Discord Developer Portal müssen die **Server Members Intent** und
  **Message Content Intent** aktiviert sein.
- Der Token gehört in die `.env` – niemals ins Git oder in ein ZIP zum Teilen
  (beim Hosting-ZIP darf er mit, weil nur du es hochlädst).
- Alles wird in `data/primeffa.db` gespeichert und überlebt Neustarts.
