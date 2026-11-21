"""Giveaway-System mit Buttons, Gewinnerziehung & Neustart-Sicherheit."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import time

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import (
    COLOR_DARK,
    COLOR_MAIN,
    COLOR_SUCCESS,
    GIVEAWAY_LOOP_INTERVAL,
    GIVEAWAY_MIN_SECONDS,
)
from utils import base_embed, error_embed, success_embed, ts

log = logging.getLogger("primeffa.giveaway")


def parse_duration(text: str) -> int:
    """'2d', '1h30m', '45s' -> Sekunden."""
    m = re.fullmatch(
        r"(?:(\d+)\s*d)?\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+)\s*s)?",
        text.strip().lower(),
    )
    if not m or not any(m.groups()):
        raise ValueError("Unbekanntes Format")
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def giveaway_embed(g: dict, *, ended: bool = False) -> discord.Embed:
    entrants = db.parse_entrants(g.get("entrants", "[]"))
    winners_list = db.parse_entrants(g.get("winners_list", "[]"))

    if not ended:
        e = base_embed(
            "🎉 Giveaway",
            (
                f"**Preis:** {g['prize']}\n"
                f"**Gewinner:** {g['winners']}\n"
                f"**Endet:** <t:{int(g['ends_at'])}:R> (<t:{int(g['ends_at'])}:f>)\n"
                f"**Teilnehmer:** {len(entrants)}\n\n"
                "Klicke auf **🎉 Teilnehmen**, um mitzumachen!"
            ),
            color=COLOR_MAIN,
        )
        e.set_footer(text=f"Gehostet von ID {g['host_id']} • PrimeFFA 🩵")
    else:
        if g.get("cancelled"):
            title = "🚫 Giveaway abgebrochen"
            desc = f"**Preis:** {g['prize']}\nDieses Giveaway wurde beendet."
            color = COLOR_DARK
        else:
            title = "🎉 Giveaway beendet!"
            if winners_list:
                mentions = "\n".join(f"🎉 <@{w}>" for w in winners_list)
                desc = (
                    f"**Preis:** {g['prize']}\n\n"
                    f"**Gewinner:**\n{mentions}\n\n"
                    "Glückwunsch! 🩵"
                )
            else:
                desc = (
                    f"**Preis:** {g['prize']}\n\n"
                    "Leider haben nicht genug Leute teilgenommen."
                )
            color = COLOR_SUCCESS
        e = base_embed(title, desc, color=color)
        e.set_footer(text=f"Teilnehmer: {len(entrants)} • PrimeFFA 🩵")

    return e


def mention_list(ids: list[int]) -> str:
    return ", ".join(f"<@{i}>" for i in ids)


# --------------------------------------------------------------------- Views

class GiveawayJoinButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            custom_id="giveaway_join",
            label="Teilnehmen",
            emoji="🎉",
            style=discord.ButtonStyle.secondary,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = interaction.client.get_cog("Giveaways")
        if cog is None:
            return await interaction.response.send_message(
                embed=error_embed("Giveaway-System nicht geladen."), ephemeral=True
            )
        await cog.toggle_join(interaction)


class GiveawayView(discord.ui.View):
    """Persistente View – funktioniert nach Neustarts weiter."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(GiveawayJoinButton())


# ---------------------------------------------------------------------- Cog

class Giveaways(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._task: asyncio.Task | None = None

    async def cog_load(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def cog_unload(self) -> None:
        if self._task:
            self._task.cancel()

    # ------------------------------------------------------------- Loop
    async def _loop(self) -> None:
        try:
            await self.bot.wait_until_ready()
        except RuntimeError:  # Bot wurde nie eingeloggt (z. B. Testlauf)
            return
        while not self.bot.is_closed():
            try:
                for g in db.due_giveaways(time.time()):
                    await self.end_giveaway(g)
            except Exception:
                log.exception("Giveaway-Loop-Fehler")
            await asyncio.sleep(GIVEAWAY_LOOP_INTERVAL)

    # ------------------------------------------------------------- Join
    async def toggle_join(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        g = db.get_giveaway_by_message(interaction.message.id)
        if not g or g["ended"]:
            return await interaction.followup.send(
                embed=error_embed("Dieses Giveaway ist bereits beendet."), ephemeral=True
            )

        entrants = db.parse_entrants(g["entrants"])
        uid = interaction.user.id
        if uid in entrants:
            entrants.remove(uid)
            db.set_entrants(g["id"], entrants)
            embed = giveaway_embed({**g, "entrants": json.dumps(entrants)})
            try:
                await interaction.message.edit(embed=embed, view=GiveawayView())
            except discord.HTTPException:
                pass
            return await interaction.followup.send(
                embed=success_embed("Abgemeldet", "Du nimmst nicht mehr teil."),
                ephemeral=True,
            )

        entrants.append(uid)
        db.set_entrants(g["id"], entrants)
        embed = giveaway_embed({**g, "entrants": json.dumps(entrants)})
        try:
            await interaction.message.edit(embed=embed, view=GiveawayView())
        except discord.HTTPException:
            pass
        await interaction.followup.send(
            embed=success_embed(
                "🎉 Dabei!",
                f"Du nimmst am Giveaway **{g['prize']}** teil.\n"
                f"Aktuell **{len(entrants)}** Teilnehmer.",
            ),
            ephemeral=True,
        )

    # -------------------------------------------------------------- Ende
    async def end_giveaway(self, g: dict, cancelled: bool = False) -> None:
        channel = self.bot.get_channel(g["channel_id"])
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(g["channel_id"])
            except (discord.HTTPException, discord.Forbidden):
                db.finish_giveaway(g["id"], [], cancelled=True)
                return
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        entrants = db.parse_entrants(g["entrants"])
        if cancelled:
            winners: list[int] = []
        else:
            count = min(int(g["winners"]), len(entrants))
            winners = random.sample(entrants, count) if count > 0 else []

        db.finish_giveaway(g["id"], winners, cancelled=cancelled)
        g = {**g, "ended": 1, "cancelled": 1 if cancelled else 0,
             "winners_list": json.dumps(winners)}

        message = None
        try:
            message = await channel.fetch_message(g["message_id"])
        except (discord.HTTPException, discord.NotFound):
            pass

        embed = giveaway_embed(g, ended=True)
        if message:
            try:
                await message.edit(embed=embed, view=None)
            except discord.HTTPException:
                log.warning("Giveaway-Nachricht konnte nicht bearbeitet werden")

        if cancelled:
            await channel.send(
                embed=base_embed(
                    "🚫 Giveaway abgebrochen",
                    f"Das Giveaway **{g['prize']}** wurde beendet.",
                    color=COLOR_DARK,
                )
            )
        elif winners:
            await channel.send(
                content=mention_list(winners),
                embed=base_embed(
                    "🎉 Gewinner ermittelt!",
                    f"**{g['prize']}**\nGewinner: {mention_list(winners)}\n\n"
                    "Glückwunsch! 🩵",
                    color=COLOR_SUCCESS,
                ),
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        else:
            await channel.send(
                embed=base_embed(
                    "🎉 Giveaway beendet",
                    f"**{g['prize']}** – keine gültigen Teilnehmer.",
                    color=COLOR_DARK,
                )
            )
        log.info("Giveaway %s beendet (Gewinner: %s)", g["id"], winners)

    async def reroll(self, g: dict) -> list[int]:
        entrants = db.parse_entrants(g["entrants"])
        old = db.parse_entrants(g.get("winners_list", "[]"))
        pool = [e for e in entrants if e not in old] or entrants
        count = min(int(g["winners"]), len(pool))
        winners = random.sample(pool, count) if count > 0 else []
        db.set_entrants(g["id"], entrants)
        with db._lock:
            db._conn.execute(  # noqa: SLF001
                "UPDATE giveaways SET winners_list=? WHERE id=?",
                (json.dumps(winners), g["id"]),
            )
            db._conn.commit()  # noqa: SLF001
        return winners

    # ---------------------------------------------------------- Commands
    @app_commands.command(
        name="giveaway", description="🎉 Ein Giveaway erstellen"
    )
    @app_commands.describe(
        prize="Preis des Giveaways",
        duration="Laufzeit, z. B. 10m, 1h, 2d",
        winners="Anzahl der Gewinner (1-20)",
        channel="Channel (Standard: gesetzter Giveaway-Channel, sonst aktueller)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway(
        self,
        interaction: discord.Interaction,
        prize: str,
        duration: str,
        winners: app_commands.Range[int, 1, 20] = 1,
        channel: discord.TextChannel = None,
    ) -> None:
        try:
            seconds = parse_duration(duration)
        except ValueError:
            return await interaction.response.send_message(
                embed=error_embed(
                    "Ungültiges Format. Beispiele: `10m`, `1h`, `1h30m`, `2d`"
                ),
                ephemeral=True,
            )
        if seconds < GIVEAWAY_MIN_SECONDS:
            return await interaction.response.send_message(
                embed=error_embed(
                    f"Mindest-Laufzeit: **{GIVEAWAY_MIN_SECONDS} Sekunden**."
                ),
                ephemeral=True,
            )

        target = channel
        if target is None:
            default_id = db.get_setting(interaction.guild_id, "giveaway_channel")
            if default_id and interaction.guild:
                default = interaction.guild.get_channel(int(default_id))
                if isinstance(default, discord.TextChannel):
                    target = default
        if target is None:
            target = interaction.channel
        if not isinstance(target, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message(
                embed=error_embed("Kein gültiger Text-Channel."), ephemeral=True
            )

        ends_at = time.time() + seconds
        gid = db.add_giveaway(
            interaction.guild_id,
            target.id,
            None,
            prize,
            winners,
            interaction.user.id,
            ends_at,
        )
        g = db.get_giveaway(gid)
        assert g is not None

        embed = giveaway_embed(g)
        if interaction.guild and interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        try:
            msg = await target.send(embed=embed, view=GiveawayView())
        except discord.HTTPException:
            db._ex("DELETE FROM giveaways WHERE id=?", (gid,))
            return await interaction.response.send_message(
                embed=error_embed("Giveaway konnte nicht gesendet werden."),
                ephemeral=True,
            )
        db.set_giveaway_message(gid, msg.id)

        e = success_embed(
            "Giveaway erstellt",
            (
                f"**Preis:** {prize}\n"
                f"**Gewinner:** {winners}\n"
                f"**Endet:** <t:{int(ends_at)}:R>\n"
                f"**Channel:** {target.mention}"
            ),
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=e, ephemeral=True)
        else:
            await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(name="giveaway-end", description="🎉 Giveaway sofort beenden")
    @app_commands.describe(message_id="ID der Giveaway-Nachricht (leer = letztes aktives im Channel)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_end(
        self, interaction: discord.Interaction, message_id: str = None
    ) -> None:
        g = await self._find_giveaway(interaction, message_id)
        if g is None:
            return
        await interaction.response.send_message(
            embed=success_embed(
                "Giveaway beendet", f"**{g['prize']}** wird jetzt ausgelost."
            ),
            ephemeral=True,
        )
        await self.end_giveaway(g)

    @app_commands.command(
        name="giveaway-reroll", description="🎉 Giveaway neu auslosen"
    )
    @app_commands.describe(message_id="ID der Giveaway-Nachricht (leer = letztes im Channel)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_reroll(
        self, interaction: discord.Interaction, message_id: str = None
    ) -> None:
        g = await self._find_giveaway(interaction, message_id, require_ended=True)
        if g is None:
            return
        # Sofort antworten – Reaktionen auslesen dauert zu lange für 3 Sekunden
        await interaction.response.defer(ephemeral=True)
        winners = await self.reroll(g)
        await interaction.followup.send(
            embed=base_embed(
                "🎉 Neue Gewinner",
                (
                    f"**{g['prize']}**\n"
                    + (f"Neue Gewinner: {mention_list(winners)}" if winners else
                       "Keine Teilnehmer vorhanden.")
                ),
                color=COLOR_SUCCESS,
            ),
            allowed_mentions=discord.AllowedMentions(users=True),
        )

    @app_commands.command(
        name="giveaway-cancel", description="🎉 Giveaway abbrechen"
    )
    @app_commands.describe(message_id="ID der Giveaway-Nachricht")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def giveaway_cancel(
        self, interaction: discord.Interaction, message_id: str = None
    ) -> None:
        g = await self._find_giveaway(interaction, message_id)
        if g is None:
            return
        await interaction.response.send_message(
            embed=success_embed("Abgebrochen", f"**{g['prize']}** wurde abgebrochen."),
            ephemeral=True,
        )
        await self.end_giveaway(g, cancelled=True)

    # ------------------------------------------------------------- Helper
    async def _find_giveaway(
        self,
        interaction: discord.Interaction,
        message_id: str | None,
        require_ended: bool = False,
    ) -> dict | None:
        if message_id:
            try:
                g = db.get_giveaway_by_message(int(message_id.strip()))
            except ValueError:
                g = None
            if not g:
                await interaction.response.send_message(
                    embed=error_embed("Kein Giveaway mit dieser Nachricht-ID gefunden."),
                    ephemeral=True,
                )
                return None
        else:
            g = db.latest_active_giveaway(interaction.guild_id, interaction.channel_id)
            if require_ended and g:
                g = None
            if not g:
                # Suche zuletzt beendetes Giveaway im Channel
                rows = [
                    dict(r)
                    for r in db._q(  # noqa: SLF001
                        "SELECT * FROM giveaways WHERE guild_id=? AND channel_id=? "
                        "ORDER BY id DESC LIMIT 1",
                        (interaction.guild_id, interaction.channel_id),
                    )
                ]
                g = rows[0] if rows else None
            if not g:
                await interaction.response.send_message(
                    embed=error_embed("Kein passendes Giveaway gefunden."),
                    ephemeral=True,
                )
                return None

        if require_ended and not g["ended"]:
            await interaction.response.send_message(
                embed=error_embed("Dieses Giveaway läuft noch. Nutze `/giveaway-end`."),
                ephemeral=True,
            )
            return None
        if not require_ended and g["ended"]:
            await interaction.response.send_message(
                embed=error_embed("Dieses Giveaway ist bereits beendet."),
                ephemeral=True,
            )
            return None
        return g


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Giveaways(bot))
