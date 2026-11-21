"""PrimeFFA Bot – Haupteinstieg."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Windows-Konsole: UTF-8, damit Emojis/Namen im Logging nicht crashen
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# .env aus Projektordner laden
load_dotenv(BASE_DIR / ".env")

import database as db  # noqa: E402
from config import BRAND_NAME, COLOR_MAIN, FOOTER_TEXT  # noqa: E402

# ------------------------------------------------------------------ Logging
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-22s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "bot.log", encoding="utf-8"),
    ],
)
logging.getLogger("discord").setLevel(logging.WARNING)
log = logging.getLogger("primeffa")

COGS = [
    "cogs.admin",
    "cogs.welcome",
    "cogs.tickets",
    "cogs.giveaway",
    "cogs.counting",
    "cogs.voiceping",
]

# Hosting-Konsole fordert hier einen SAUBEREN Shutdown an (Discord-Logout,
# damit der Bot im Server sofort offline wird). Wird von der Konsole geleert.
STOP_REQUEST = BASE_DIR / "data" / "shutdown.request"


class PrimeFFABot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        intents.reactions = True
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
            help_command=None,
            activity=None,
        )
        self.start_time = time.time()
        self.logger = log
        # Slash-Command-Fehlerbehandlung (discord.py 2.x: über den Tree)
        self.tree.on_error = self._on_app_command_error

    # -------------------------------------------------------------- Setup
    async def setup_hook(self) -> None:
        db.init()
        for cog in COGS:
            try:
                await self.load_extension(cog)
                log.info("Cog geladen: %s", cog)
            except Exception:
                log.exception("Cog konnte nicht geladen werden: %s", cog)

        # Wachhund für sauberes Herunterfahren aus der Hosting-Konsole
        self._shutdown_task = asyncio.create_task(self._watch_shutdown_request())

        # Persistente Views (funktionieren nach Neustart weiter)
        from cogs.admin import SetupMenuView
        from cogs.giveaway import GiveawayView
        from cogs.tickets import LegacyTicketControlView, TicketControlView, TicketPanelView

        self.add_view(TicketPanelView())
        self.add_view(TicketControlView())
        self.add_view(LegacyTicketControlView())
        self.add_view(GiveawayView())
        self.add_view(SetupMenuView())

        # Slash-Commands synchronisieren
        try:
            test_guild = os.getenv("TEST_GUILD_ID", "").strip()
            if test_guild and test_guild.isdigit():
                guild = discord.Object(id=int(test_guild))
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                log.info(
                    "Commands sofort für Test-Server %s synchronisiert.", test_guild
                )
            synced = await self.tree.sync()
            log.info("%d Slash-Commands synchronisiert.", len(synced))
        except Exception:
            log.exception("Slash-Command-Sync fehlgeschlagen")

    async def on_ready(self) -> None:
        if self.user:
            log.info(
                "Eingeloggt als %s (ID: %s) | %d Server",
                self.user,
                self.user.id,
                len(self.guilds),
            )
        await self.change_presence(activity=discord.Game(name=BRAND_NAME))

    # ----------------------------------------------------- Sauberer Shutdown
    async def _watch_shutdown_request(self) -> None:
        """Prüft alle 1 s, ob die Konsole einen sauberen Stop angefordert hat.

        Beim Stop wird die Discord-Verbindung ordnungsgemäß getrennt
        (bot.close()), damit der Bot im Server SOFORT offline erscheint
        und nicht als "online" hängen bleibt.
        """
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                if STOP_REQUEST.exists():
                    log.info(
                        "Shutdown angefordert – trenne Discord-Verbindung sauber ..."
                    )
                    try:
                        STOP_REQUEST.unlink()
                    except OSError:
                        pass
                    await self.close()
                    return
            except Exception:
                log.exception("Shutdown-Watcher-Fehler")
            await asyncio.sleep(1.0)

    # ------------------------------------------------------ Fehlerbehandlung
    async def _on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        original = getattr(error, "original", error)
        if isinstance(error, app_commands.CheckFailure):
            msg = "❌ Du hast keine Berechtigung, diesen Befehl zu nutzen."
        elif isinstance(error, app_commands.MissingPermissions):
            msg = "❌ Dir fehlen die nötigen Berechtigungen."
        elif isinstance(error, app_commands.CommandOnCooldown):
            msg = f"⏳ Bitte warte {error.retry_after:.1f} Sekunden."
        else:
            log.exception("Fehler in Slash-Command", exc_info=original)
            msg = "❌ Es ist ein Fehler aufgetreten. Bitte versuche es erneut."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            log.exception("Fehler beim Senden der Fehlermeldung")

    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        log.warning("Prefix-Command-Fehler: %s", error)


def main() -> None:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token or "HIER" in token.upper() or token.count(".") < 2:
        log.error(
            "DISCORD_TOKEN fehlt oder ist noch ein Platzhalter!\n"
            "  1. Trage deinen Token in die Datei .env ein: DISCORD_TOKEN=dein_token\n"
            "  2. Token bekommst du unter https://discord.com/developers/applications"
        )
        sys.exit(1)

    bot = PrimeFFABot()
    log.info("Starte %s ...", BRAND_NAME)
    try:
        bot.run(token, log_handler=None)
    except discord.LoginFailure:
        log.error(
            "Ungültiger Bot-Token! Kopiere ihn erneut aus dem Discord Developer "
            "Portal und trage ihn in der .env-Datei ein."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
