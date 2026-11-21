"""Voice-Rang-Ping-System: Rollen-Ping beim Betreten eines Voice-Channels."""

from __future__ import annotations

import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import COLOR_DARK, COLOR_MAIN
from utils import base_embed, error_embed, success_embed

log = logging.getLogger("primeffa.voiceping")

DEFAULT_MESSAGE = "🔔 {roles} – jemand ist in **{voice}** beigetreten!"


class VoicePing(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------- Events
    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot or not member.guild:
            return

        cfg = db.get_voice_ping(member.guild.id)
        if not cfg:
            return
        voice_id = cfg.get("voice_channel_id")
        text_id = cfg.get("text_channel_id")
        if not voice_id or not text_id or not cfg.get("roles"):
            return

        # Nur wenn jemand DEN ausgewählten Channel betritt (nicht Wechsel innerhalb)
        if after.channel is None or after.channel.id != voice_id:
            return
        if before.channel is not None and before.channel.id == voice_id:
            return

        # Spam-Schutz (Cooldown)
        cooldown = int(cfg.get("cooldown") or 60)
        now = time.time()
        if now - float(cfg.get("last_ping") or 0) < cooldown:
            log.info("Voice-Ping übersprungen (Cooldown) in %s", member.guild.name)
            return

        channel = member.guild.get_channel(text_id)
        if not isinstance(channel, discord.TextChannel):
            return

        role_mentions = " ".join(f"<@&{rid}>" for rid in cfg["roles"])
        template = cfg.get("message") or DEFAULT_MESSAGE
        content = (
            template.replace("{roles}", role_mentions)
            .replace("{voice}", after.channel.name)
            .replace("{user}", member.mention)
        )

        e = base_embed(
            "🔔 Jemand ist im Voice!",
            f"{member.mention} ist **{after.channel.name}** beigetreten.",
            color=COLOR_MAIN,
        )
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="Voice-Channel", value=after.channel.mention, inline=True)

        try:
            await channel.send(
                content=content,
                embed=e,
                allowed_mentions=discord.AllowedMentions(roles=True, users=True),
            )
            db.set_voice_ping_last(member.guild.id, now)
        except discord.HTTPException as exc:
            log.warning("Voice-Ping fehlgeschlagen: %s", exc)

    # ------------------------------------------------------------ Commands
    @app_commands.command(
        name="voice-ping-setup",
        description="🔔 Voice-Rang-Ping einrichten (Rollen werden gepingt)",
    )
    @app_commands.describe(
        voice_channel="Voice-Channel, der überwacht wird",
        text_channel="Text-Channel, in dem gepingt wird",
        role1="Rolle 1 (Pflicht)",
        role2="Rolle 2 (optional)",
        role3="Rolle 3 (optional)",
        role4="Rolle 4 (optional)",
        role5="Rolle 5 (optional)",
        message="Eigene Nachricht ({roles}, {voice}, {user} möglich)",
        cooldown="Spam-Schutz in Sekunden (Standard: 60)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voice_ping_setup(
        self,
        interaction: discord.Interaction,
        voice_channel: discord.VoiceChannel,
        text_channel: discord.TextChannel,
        role1: discord.Role,
        role2: discord.Role = None,
        role3: discord.Role = None,
        role4: discord.Role = None,
        role5: discord.Role = None,
        message: str = None,
        cooldown: app_commands.Range[int, 5, 86400] = 60,
    ) -> None:
        roles = [r for r in (role1, role2, role3, role4, role5) if r is not None]
        db.set_voice_ping(
            interaction.guild_id,
            voice_channel.id,
            text_channel.id,
            [r.id for r in roles],
            message,
            cooldown,
        )
        role_list = "\n".join(f"- {r.mention}" for r in roles)
        e = base_embed(
            "🔔 Voice-Ping eingerichtet",
            (
                f"**Voice-Channel:** {voice_channel.mention}\n"
                f"**Text-Channel:** {text_channel.mention}\n"
                f"**Cooldown:** {cooldown}s\n"
                f"**Rollen:**\n{role_list}\n"
                f"**Nachricht:**\n{message or DEFAULT_MESSAGE}"
            ),
            color=COLOR_MAIN,
        )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(
        name="voice-ping-disable", description="🔔 Voice-Ping deaktivieren"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def voice_ping_disable(self, interaction: discord.Interaction) -> None:
        db._ex("DELETE FROM voice_ping WHERE guild_id=?", (interaction.guild_id,))
        db.delete_setting(interaction.guild_id, "voice_ping_text_channel")
        await interaction.response.send_message(
            embed=success_embed("Deaktiviert", "Voice-Ping ist aus."),
            ephemeral=True,
        )

    @app_commands.command(
        name="voice-ping-status", description="🔔 Aktuellen Voice-Ping anzeigen"
    )
    async def voice_ping_status(self, interaction: discord.Interaction) -> None:
        cfg = db.get_voice_ping(interaction.guild_id)
        if not cfg:
            return await interaction.response.send_message(
                embed=error_embed("Voice-Ping ist noch nicht eingerichtet."),
                ephemeral=True,
            )
        roles = " ".join(f"<@&{r}>" for r in cfg["roles"]) or "-"
        last = (
            f"<t:{int(cfg['last_ping'])}:R>"
            if cfg.get("last_ping")
            else "noch nie"
        )
        e = base_embed(
            "🔔 Voice-Ping Status",
            (
                f"**Voice:** <#{cfg['voice_channel_id']}>\n"
                f"**Text:** <#{cfg['text_channel_id']}>\n"
                f"**Rollen:** {roles}\n"
                f"**Cooldown:** {cfg['cooldown']}s\n"
                f"**Letzter Ping:** {last}"
            ),
            color=COLOR_DARK,
        )
        await interaction.response.send_message(embed=e, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VoicePing(bot))
