"""Counting-System: fortlaufend zählen mit Rekord & Fehler-Reset."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import COLOR_DARK, COLOR_MAIN, COLOR_SUCCESS
from utils import base_embed, error_embed, success_embed, warn_embed

log = logging.getLogger("primeffa.counting")


class Counting(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------- Events
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        if message.channel.type != discord.ChannelType.text:
            return

        cfg = db.get_counting(message.guild.id)
        if not cfg or cfg.get("channel_id") != message.channel.id:
            return

        # Nur ganze Zahlen zulassen
        content = message.content.strip().replace(" ", "")
        try:
            num = int(content)
        except ValueError:
            return  # andere Nachrichten ignorieren

        expected = int(cfg["current"]) + 1
        last_user = cfg.get("last_user")
        same_user = last_user is not None and int(last_user) == message.author.id

        # Fehler: falsche Zahl oder zweite Zahl desselben Users -> Reset
        if num != expected or same_user:
            reason = (
                f"Falsche Zahl! Erwartet war **{expected}**."
                if num != expected
                else "Zwei Zahlen hintereinander vom selben User!"
            )
            db.reset_counting(message.guild.id)
            e = warn_embed(
                "❌ Zähler zurückgesetzt",
                f"{reason}\n\n{message.author.mention}, wir starten wieder bei **1**.",
            )
            e.set_thumbnail(url=message.author.display_avatar.url)
            await message.channel.send(embed=e, delete_after=15)
            try:
                await message.add_reaction("❌")
            except discord.HTTPException:
                pass
            return

        # Korrekt
        db.update_counting(message.guild.id, num, message.author.id)
        try:
            await message.add_reaction("✅")
        except discord.HTTPException:
            pass

        record = int(cfg["record"])
        if num > record:
            db.set_counting_record(message.guild.id, num)
            e = base_embed(
                "🎉 Neuer Rekord!",
                f"{message.author.mention} hat **{num}** erreicht – neuer Serverrekord!",
                color=COLOR_SUCCESS,
            )
            await message.channel.send(embed=e, delete_after=15)

    # ------------------------------------------------------------ Commands
    @app_commands.command(
        name="counting-setup", description="🔢 Counting-Channel einrichten"
    )
    @app_commands.describe(channel="Channel, in dem gezählt wird")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def counting_setup(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        db.set_counting_channel(interaction.guild_id, channel.id)
        cfg = db.get_counting(interaction.guild_id) or {}
        e = base_embed(
            "🔢 Counting-System eingerichtet",
            (
                f"**Channel:** {channel.mention}\n"
                f"**Aktuelle Zahl:** {cfg.get('current', 0)}\n"
                f"**Rekord:** {cfg.get('record', 0)}\n\n"
                "Regeln:\n"
                "• Zahlen fortlaufend im Chat posten\n"
                "• Keine zwei Zahlen hintereinander vom selben User\n"
                "• Bei Fehlern wird auf **0** zurückgesetzt"
            ),
            color=COLOR_MAIN,
        )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(
        name="counting-reset", description="🔢 Zähler zurücksetzen"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def counting_reset(self, interaction: discord.Interaction) -> None:
        db.reset_counting(interaction.guild_id)
        await interaction.response.send_message(
            embed=success_embed("Zurückgesetzt", "Der Zähler steht wieder auf **0**."),
            ephemeral=True,
        )

    @app_commands.command(
        name="counting-record", description="🔢 Rekord des Counting-Systems anzeigen"
    )
    async def counting_record(self, interaction: discord.Interaction) -> None:
        cfg = db.get_counting(interaction.guild_id)
        if not cfg:
            return await interaction.response.send_message(
                embed=error_embed("Counting ist noch nicht eingerichtet."),
                ephemeral=True,
            )
        e = base_embed(
            "🔢 Counting-Statistik",
            (
                f"**Channel:** <#{cfg['channel_id']}>\n"
                f"**Aktuelle Zahl:** {cfg['current']}\n"
                f"**Rekord:** {cfg['record']}"
            ),
            color=COLOR_DARK,
        )
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Counting(bot))
