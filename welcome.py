"""Willkommen- und Verlassen-System (Babyblaue Embeds)."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import BRAND_NAME, COLOR_DARK, COLOR_MAIN
from utils import base_embed, error_embed, success_embed

log = logging.getLogger("primeffa.welcome")

DEFAULT_WELCOME = (
    "Willkommen auf **{server}**, {user}! 🩵\n\n"
    "Du bist unser Mitglied **#{count}**.\n"
    "Viel Spaß auf dem Server!"
)
DEFAULT_LEAVE = (
    "**{user}** hat **{server}** verlassen. 👋\n\n"
    "Noch **{count}** Mitglieder – wir sehen uns!"
)


def fill(template: str, member: discord.Member, guild: discord.Guild) -> str:
    return (
        template.replace("{user}", member.mention)
        .replace("{username}", member.name)
        .replace("{server}", guild.name)
        .replace("{count}", str(guild.member_count))
    )


class WelcomeLeave(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------- Autorolle
    async def give_autoroll(self, member: discord.Member) -> None:
        """Vergebt die Autorolle an neue Mitglieder, wenn sie gesetzt ist."""
        rid = db.get_int(member.guild.id, "autoroll_role", 0)
        if not rid:
            return
        role = member.guild.get_role(rid)
        if role is None or role.is_default() or role.managed or role in member.roles:
            return
        try:
            await member.add_roles(role, reason="PrimeFFA Autorolle")
            log.info("Autorolle '%s' an %s vergeben", role.name, member)
        except discord.HTTPException:
            log.warning(
                "Autorolle fehlgeschlagen (%s) auf %s", role.name, member.guild.name
            )

    # ------------------------------------------------------ Events
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot or not member.guild:
            return

        # Autorolle: neue Mitglieder bekommen sofort ihre Rolle
        await self.give_autoroll(member)

        channel_id = db.get_int(member.guild.id, "welcome_channel", 0)
        if not channel_id:
            return
        channel = member.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        template = db.get_setting(member.guild.id, "welcome_message") or DEFAULT_WELCOME
        e = base_embed(
            f"🩵 Willkommen bei {BRAND_NAME}!",
            fill(template, member, member.guild),
            color=COLOR_MAIN,
        )
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="Mitglied", value=member.mention, inline=True)
        e.add_field(
            name="Mitgliederanzahl", value=str(member.guild.member_count), inline=True
        )
        e.add_field(
            name="Konto erstellt",
            value=f"<t:{int(member.created_at.timestamp())}:R>",
            inline=True,
        )
        e.set_footer(text=f"{BRAND_NAME} • Mitglied #{member.guild.member_count}")
        try:
            await channel.send(embed=e)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.bot or not member.guild:
            return
        channel_id = db.get_int(member.guild.id, "leave_channel", 0)
        if not channel_id:
            return
        channel = member.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return

        template = db.get_setting(member.guild.id, "leave_message") or DEFAULT_LEAVE
        e = base_embed(
            "🚪 Auf Wiedersehen",
            fill(template, member, member.guild),
            color=COLOR_DARK,
        )
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="Mitglieder", value=str(member.guild.member_count), inline=True)
        try:
            await channel.send(embed=e)
        except discord.HTTPException:
            pass

    # ------------------------------------------------------ Commands
    @app_commands.command(
        name="welcome-setup", description="👋 Willkommens-Channel einrichten"
    )
    @app_commands.describe(
        channel="Channel für Willkommensnachrichten",
        message="Eigene Nachricht ({user}, {username}, {server}, {count} möglich)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str = None,
    ) -> None:
        db.set_setting(interaction.guild_id, "welcome_channel", channel.id)
        if message:
            db.set_setting(interaction.guild_id, "welcome_message", message)

        e = base_embed(
            "👋 Willkommen-System eingerichtet",
            (
                f"**Channel:** {channel.mention}\n"
                f"**Nachricht:**\n{message or DEFAULT_WELCOME}"
            ),
            color=COLOR_MAIN,
        )
        # Testnachricht
        preview = base_embed(
            f"🩵 Willkommen bei {BRAND_NAME}!",
            (message or DEFAULT_WELCOME)
            .replace("{user}", interaction.user.mention)
            .replace("{username}", interaction.user.name)
            .replace("{server}", interaction.guild.name if interaction.guild else "")
            .replace("{count}", str(interaction.guild.member_count if interaction.guild else 0)),
            color=COLOR_MAIN,
        )
        preview.set_thumbnail(url=interaction.user.display_avatar.url)
        try:
            await channel.send(embed=preview)
        except discord.HTTPException:
            pass
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(
        name="leave-setup", description="🚪 Verlassen-Channel einrichten"
    )
    @app_commands.describe(
        channel="Channel für Verlassen-Nachrichten",
        message="Eigene Nachricht ({user}, {username}, {server}, {count} möglich)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def leave_setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str = None,
    ) -> None:
        db.set_setting(interaction.guild_id, "leave_channel", channel.id)
        if message:
            db.set_setting(interaction.guild_id, "leave_message", message)

        e = base_embed(
            "🚪 Verlassen-System eingerichtet",
            f"**Channel:** {channel.mention}\n**Nachricht:**\n{message or DEFAULT_LEAVE}",
            color=COLOR_DARK,
        )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(
        name="autoroll-setup",
        description="🔰 Autorolle für neue Mitglieder einrichten",
    )
    @app_commands.describe(
        role="Rolle, die neue Mitglieder automatisch bekommen (leer = deaktivieren)"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def autoroll_setup(
        self, interaction: discord.Interaction, role: discord.Role = None
    ) -> None:
        if role is None:
            db.delete_setting(interaction.guild_id, "autoroll_role")
            return await interaction.response.send_message(
                embed=success_embed(
                    "Autorolle deaktiviert",
                    "Neue Mitglieder bekommen keine Rolle mehr.",
                ),
                ephemeral=True,
            )
        if role.is_default() or role.managed:
            return await interaction.response.send_message(
                embed=error_embed("Diese Rolle kann nicht verwendet werden."),
                ephemeral=True,
            )
        db.set_setting(interaction.guild_id, "autoroll_role", role.id)
        await interaction.response.send_message(
            embed=success_embed(
                "Autorolle aktiv",
                (
                    f"Neue Mitglieder bekommen automatisch {role.mention}.\n"
                    f"**Position:** `{role.position}` – muss über `@everyone` liegen, "
                    "sonst klappt es nicht."
                ),
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="welcome-disable", description="👋 Willkommensnachricht deaktivieren"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome_disable(self, interaction: discord.Interaction) -> None:
        db.delete_setting(interaction.guild_id, "welcome_channel")
        await interaction.response.send_message(
            embed=success_embed("Deaktiviert", "Willkommensnachrichten sind aus."),
            ephemeral=True,
        )

    @app_commands.command(
        name="leave-disable", description="🚪 Verlassen-Nachricht deaktivieren"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def leave_disable(self, interaction: discord.Interaction) -> None:
        db.delete_setting(interaction.guild_id, "leave_channel")
        await interaction.response.send_message(
            embed=success_embed("Deaktiviert", "Verlassen-Nachrichten sind aus."),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeLeave(bot))
