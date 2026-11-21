"""PrimeFFA Bot – zentrale Konfiguration & Farben."""

BRAND_NAME = "PrimeFFA"

# 🎨 Farbpalette (Babyblau)
COLOR_MAIN = 0x89CFF0      # Hauptfarbe  #89CFF0
COLOR_LIGHT = 0xBFEFFF     # Hellblau    #BFEFFF
COLOR_DARK = 0x5DADE2      # Akzent      #5DADE2
COLOR_ERROR = 0xE74C3C
COLOR_SUCCESS = 0x57F287
COLOR_WARNING = 0xFEE75C

FOOTER_TEXT = ""  # Footer-Text wird nirgends mehr angezeigt (leer = kein Footer)
AUTHOR_NAME = f"🩵 {BRAND_NAME}"

# Optional: URL zu deinem Server-/Bot-Logo (wird als Embed-Bild gesetzt)
EMBED_IMAGE_URL = ""

# Ticket-Einstellungen (Standardwerte, per Command änderbar)
DEFAULT_TICKET_CATEGORY_NAME = "🎫 Tickets"
TRANSCRIPT_LIMIT = 200      # Nachrichten pro Transkript
GIVEAWAY_MIN_SECONDS = 10   # kürzste Giveaway-Laufzeit
GIVEAWAY_LOOP_INTERVAL = 5  # Sekunden zwischen Giveaway-Checks
