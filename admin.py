"""Admin-System: /setup-Einrichtungsmenü, /config, /bot-info.

Das Setup-Menü ist eine persistente View (funktioniert nach jedem Neustart)
und speichert alle Werte dauerhaft in SQLite.
"""

from __future__ import annotations

import platform

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import BRAND_NAME, COLOR_DARK, COLOR_LIGHT, COLOR_MAIN
from utils import base_embed, error_embed, info_embed, success_embed, ts

SYSTEMS = [
    ("🎫 Ticketsystem", "/ticket-setup", "ticket_panel_channel"),
    ("👋 Willkommen", "/welcome-setup", "welcome_channel"),
    ("🚪 Verlassen", "/leave-setup", "leave_channel"),
    ("🎉 Giveaway", "/giveaway", "giveaway_channel"),
    ("🔢 Counting", "/counting-setup", "counting_channel"),
    ("🔔 Voice-Rang-Ping", "/voice-ping-setup", "voice_ping_text_channel"),
]

SETUP_OPTIONS = [
    ("tickets", "Ticketsystem", "Panel, Staff-Rolle & Log-Channel", "🎫"),
    ("welcome", "Willkommen", "Channel & Nachricht", "👋"),
    ("leave", "Verlassen", "Channel & Nachricht", "🚪"),
    ("counting", "Counting", "Zähl-Channel", "🔢"),
    ("voiceping", "Voice-Rang-Ping", "Voice-, Text-Channel & Rollen", "🔔"),
    ("giveaway", "Giveaway", "Standard-Giveaway-Channel", "🎉"),
    ("autoroll", "Autorolle", "Rolle für neue Mitglieder", "🔰"),
    ("config", "Config anzeigen", "Alle gespeicherten Werte", "⚙️"),
    ("status", "Status-Übersicht", "Alle Systeme auf einen Blick", "📊"),
]

TEXT = [discord.ChannelType.text]


def is_admin(member: discord.abc.User) -> bool:
    return isinstance(member, discord.Member) and (
        member.guild_permissions.manage_guild
        or member.guild_permissions.administrator
    )


def _channel_status(guild: discord.Guild, key: str) -> str:
    value = db.get_setting(guild.id, key)
    return f"🟢 <#{value}>" if value else "🔴 nicht eingerichtet"


def status_lines(guild: discord.Guild) -> list[str]:
    counting = db.get_counting(guild.id)
    counting_status = (
        f"🟢 <#{counting['channel_id']}> · Rekord **{counting['record']}**"
        if counting and counting.get("channel_id")
        else "🔴 nicht eingerichtet"
    )
    vp = db.get_voice_ping(guild.id)
    vp_status = (
        f"🟢 <#{vp['text_channel_id']}> ← <#{vp['voice_channel_id']}>"
        if vp and vp.get("voice_channel_id")
        else "🔴 nicht eingerichtet"
    )
    autoroll = db.get_setting(guild.id, "autoroll_role")
    autoroll_status = f"🟢 <@&{autoroll}>" if autoroll else "🔴 nicht gesetzt"
    return [
        f"🎫 Tickets: {_channel_status(guild, 'ticket_panel_channel')}",
        f"👋 Willkommen: {_channel_status(guild, 'welcome_channel')}",
        f"🚪 Verlassen: {_channel_status(guild, 'leave_channel')}",
        f"🎉 Giveaway: {_channel_status(guild, 'giveaway_channel')}",
        f"🔢 Counting: {counting_status}",
        f"🔔 Voice-Ping: {vp_status}",
        f"🔰 Autorolle: {autoroll_status}",
    ]


def status_embed(guild: discord.Guild) -> discord.Embed:
    e = base_embed(
        "📊 PrimeFFA Status",
        "\n".join(status_lines(guild)),
        color=COLOR_MAIN,
    )
    e.set_author(name=BRAND_NAME)
    e.add_field(
        name="Einrichten",
        value="Nutze das Menü unter `/setup` – alles wird sofort gespeichert.",
        inline=False,
    )
    return e


# ======================================================================
#  Persistentes Hauptmenü (überlebt Neustarts)
# ======================================================================

class SetupSelect(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            custom_id="setup_menu",
            placeholder="🩵 Wähle, was du einrichten möchtest",
            min_values=1,
            max_values=1,
            row=0,
            options=[
                discord.SelectOption(
                    label=label, value=key, description=desc, emoji=emoji
                )
                for key, label, desc, emoji in SETUP_OPTIONS
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = interaction.client.get_cog("Admin")
        if cog is None:
            return await interaction.response.send_message(
                embed=error_embed("Setup-Menü nicht geladen."), ephemeral=True
            )
        await cog.handle_menu(interaction, self.values[0])


class SetupMenuView(discord.ui.View):
    """Persistente View – bleibt nach Neustarts erhalten."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(SetupSelect())


# ======================================================================
#  Helfer für die Unter-Menüs
# ======================================================================

async def _reply(
    interaction: discord.Interaction,
    embed: discord.Embed,
    view: discord.ui.View | None = None,
    *,
    edit: bool = True,
) -> None:
    """Antwortet oder bearbeitet die aktuelle (ephemere) Nachricht."""
    if edit and interaction.response.is_done():
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
    elif edit:
        await interaction.response.edit_message(embed=embed, view=view)
    else:
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ======================================================================
#  Tickets einrichten
# ======================================================================

class TicketsPanelSelect(discord.ui.ChannelSelect):
    def __init__(self) -> None:
        super().__init__(
            channel_types=TEXT,
            placeholder="📎 Panel-Channel wählen",
            min_values=0,
            max_values=1,
            required=False,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TicketsSetupView = self.view  # type: ignore[assignment]
        view.panel_id = self.values[0].id if self.values else None
        await _reply(interaction, view.build())


class TicketsLogSelect(discord.ui.ChannelSelect):
    def __init__(self) -> None:
        super().__init__(
            channel_types=TEXT,
            placeholder="📝 Log-Channel wählen",
            min_values=0,
            max_values=1,
            required=False,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TicketsSetupView = self.view  # type: ignore[assignment]
        view.log_id = self.values[0].id if self.values else None
        await _reply(interaction, view.build())


class TicketsRoleSelect(discord.ui.RoleSelect):
    def __init__(self) -> None:
        super().__init__(
            placeholder="🛡️ Staff-Rolle wählen",
            min_values=0,
            max_values=1,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TicketsSetupView = self.view  # type: ignore[assignment]
        view.role_id = self.values[0].id if self.values else None
        await _reply(interaction, view.build())


class TicketsSaveButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="Speichern & Panel erstellen",
            emoji="✅",
            style=discord.ButtonStyle.primary,
            row=3,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: TicketsSetupView = self.view  # type: ignore[assignment]
        await view.save(interaction)


class TicketsSetupView(discord.ui.View):
    def __init__(self, gid: int) -> None:
        super().__init__(timeout=1800)
        self.gid = gid
        self.panel_id = int(db.get_setting(gid, "ticket_panel_channel") or 0) or None
        self.log_id = int(db.get_setting(gid, "ticket_log_channel") or 0) or None
        self.role_id = int(db.get_setting(gid, "ticket_staff_role") or 0) or None
        self.add_item(TicketsPanelSelect())
        self.add_item(TicketsLogSelect())
        self.add_item(TicketsRoleSelect())
        self.add_item(TicketsSaveButton())

    def build(self, note: str | None = None) -> discord.Embed:
        e = base_embed(
            "🎫 Ticketsystem einrichten",
            (
                "Wähle Kanäle und Staff-Rolle aus und klicke auf "
                "**Speichern & Panel erstellen**.\n"
                "Alles wird **dauerhaft** gespeichert.\n\n"
                f"**Panel-Channel:** {f'<#{self.panel_id}>' if self.panel_id else 'aktueller Channel'}\n"
                f"**Log-Channel:** {f'<#{self.log_id}>' if self.log_id else 'nicht gesetzt'}\n"
                f"**Staff-Rolle:** {f'<@&{self.role_id}>' if self.role_id else 'Standard (Manage Server)'}"
            ),
            color=COLOR_MAIN,
        )
        if note:
            e.add_field(name="✅", value=note, inline=False)
        return e

    async def save(self, interaction: discord.Interaction) -> None:
        gid = interaction.guild_id
        if self.panel_id:
            db.set_setting(gid, "ticket_panel_channel", self.panel_id)
        if self.log_id:
            db.set_setting(gid, "ticket_log_channel", self.log_id)
        if self.role_id:
            db.set_setting(gid, "ticket_staff_role", self.role_id)

        target = None
        if self.panel_id and interaction.guild:
            target = interaction.guild.get_channel(self.panel_id)
        if not isinstance(target, discord.TextChannel):
            target = interaction.channel
        if not isinstance(target, discord.TextChannel):
            return await _reply(
                interaction, error_embed("Kein gültiger Text-Channel."), edit=False
            )

        tickets = interaction.client.get_cog("Tickets")
        if tickets is None:
            return await _reply(
                interaction, error_embed("Ticket-System nicht geladen."), edit=False
            )

        await interaction.response.defer()
        err = await tickets.send_panel(target)
        if err:
            return await interaction.followup.edit_message(
                interaction.message.id, embed=error_embed(err), view=self
            )

        db.set_setting(gid, "ticket_panel_channel", target.id)
        await interaction.followup.edit_message(
            interaction.message.id,
            embed=success_embed(
                "Ticketsystem gespeichert",
                (
                    f"**Panel:** {target.mention}\n"
                    f"**Log-Channel:** {f'<#{self.log_id}>' if self.log_id else 'nicht gesetzt'}\n"
                    f"**Staff-Rolle:** {f'<@&{self.role_id}>' if self.role_id else 'Standard'}\n\n"
                    "Kategorie-Rollen: `/ticket-roles`"
                ),
            ),
            view=None,
        )


# ======================================================================
#  Willkommen / Verlassen einrichten
# ======================================================================

class SetupChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, kind: str) -> None:
        self.kind = kind
        label = "Willkommens-Channel" if kind == "welcome" else "Verlassen-Channel"
        super().__init__(
            channel_types=TEXT,
            placeholder=f"📌 {label} wählen",
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: MessageSetupView = self.view  # type: ignore[assignment]
        db.set_setting(interaction.guild_id, f"{self.kind}_channel", self.values[0].id)
        view.channel_id = self.values[0].id
        await _reply(
            interaction,
            view.build(note=f"✅ <#{self.values[0].id}> gespeichert"),
        )


class MessageButton(discord.ui.Button):
    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(
            label="Eigene Nachricht eingeben",
            emoji="📝",
            style=discord.ButtonStyle.secondary,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        current = db.get_setting(interaction.guild_id, f"{self.kind}_message") or ""
        await interaction.response.send_modal(MessageModal(self.kind, current))


class MessageModal(discord.ui.Modal):
    def __init__(self, kind: str, current: str) -> None:
        title = (
            "Willkommensnachricht" if kind == "welcome" else "Verlassen-Nachricht"
        )
        super().__init__(title=title)
        self.kind = kind
        self.text_input = discord.ui.TextInput(
            label="Nachricht",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1500,
            placeholder="Platzhalter: {user} {username} {server} {count}",
            default=current[:1500],
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        db.set_setting(
            interaction.guild_id, f"{self.kind}_message", str(self.text_input)
        )
        await interaction.response.send_message(
            embed=success_embed(
                "Nachricht gespeichert",
                "Die Vorlage wurde dauerhaft gespeichert.",
            ),
            ephemeral=True,
        )


class MessageSetupView(discord.ui.View):
    def __init__(self, kind: str, gid: int) -> None:
        super().__init__(timeout=1800)
        self.kind = kind
        self.gid = gid
        self.channel_id = int(db.get_setting(gid, f"{kind}_channel") or 0) or None
        self.add_item(SetupChannelSelect(kind))
        self.add_item(MessageButton(kind))

    def build(self, note: str | None = None) -> discord.Embed:
        title = (
            "👋 Willkommen einrichten"
            if self.kind == "welcome"
            else "🚪 Verlassen einrichten"
        )
        template = db.get_setting(self.gid, f"{self.kind}_message")
        e = base_embed(
            title,
            (
                "Wähle den Channel – die Einstellung wird **sofort dauerhaft "
                "gespeichert**.\n\n"
                f"**Channel:** {f'<#{self.channel_id}>' if self.channel_id else 'noch nicht gesetzt'}\n"
                f"**Nachricht:**\n{template or 'Standard-Vorlage'}"
            ),
            color=COLOR_MAIN,
        )
        if note:
            e.add_field(name="Status", value=note, inline=False)
        return e


# ======================================================================
#  Counting einrichten
# ======================================================================

class CountingChannelSelect(discord.ui.ChannelSelect):
    def __init__(self) -> None:
        super().__init__(
            channel_types=TEXT,
            placeholder="🔢 Zähl-Channel wählen",
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: CountingSetupView = self.view  # type: ignore[assignment]
        db.set_counting_channel(interaction.guild_id, self.values[0].id)
        view.channel_id = self.values[0].id
        await _reply(
            interaction,
            view.build(note=f"✅ <#{self.values[0].id}> gespeichert"),
        )


class CountingResetButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="Zähler zurücksetzen",
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        db.reset_counting(interaction.guild_id)
        view: CountingSetupView = self.view  # type: ignore[assignment]
        await _reply(interaction, view.build(note="🔄 Zähler steht auf 0"))


class CountingSetupView(discord.ui.View):
    def __init__(self, gid: int) -> None:
        super().__init__(timeout=1800)
        self.gid = gid
        cfg = db.get_counting(gid)
        self.channel_id = cfg.get("channel_id") if cfg else None
        self.record = cfg.get("record", 0) if cfg else 0
        self.add_item(CountingChannelSelect())
        self.add_item(CountingResetButton())

    def build(self, note: str | None = None) -> discord.Embed:
        e = base_embed(
            "🔢 Counting einrichten",
            (
                "Wähle den Zähl-Channel – wird **sofort dauerhaft gespeichert**.\n\n"
                f"**Channel:** {f'<#{self.channel_id}>' if self.channel_id else 'noch nicht gesetzt'}\n"
                f"**Rekord:** {self.record}"
            ),
            color=COLOR_MAIN,
        )
        if note:
            e.add_field(name="Status", value=note, inline=False)
        return e


# ======================================================================
#  Voice-Rang-Ping einrichten
# ======================================================================

class VpVoiceSelect(discord.ui.ChannelSelect):
    def __init__(self) -> None:
        super().__init__(
            channel_types=[discord.ChannelType.voice],
            placeholder="🔊 Voice-Channel wählen",
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: VoicePingSetupView = self.view  # type: ignore[assignment]
        view.voice_id = self.values[0].id
        await _reply(interaction, view.build())


class VpTextSelect(discord.ui.ChannelSelect):
    def __init__(self) -> None:
        super().__init__(
            channel_types=TEXT,
            placeholder="💬 Text-Channel (dort wird gepingt)",
            min_values=1,
            max_values=1,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: VoicePingSetupView = self.view  # type: ignore[assignment]
        view.text_id = self.values[0].id
        await _reply(interaction, view.build())


class VpRoleSelect(discord.ui.RoleSelect):
    def __init__(self) -> None:
        super().__init__(
            placeholder="🔔 Rollen, die gepingt werden (mehrfach)",
            min_values=1,
            max_values=5,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: VoicePingSetupView = self.view  # type: ignore[assignment]
        view.roles = [r.id for r in self.values]
        await _reply(interaction, view.build())


class VpSaveButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="Speichern",
            emoji="✅",
            style=discord.ButtonStyle.primary,
            row=3,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: VoicePingSetupView = self.view  # type: ignore[assignment]
        if not view.voice_id or not view.text_id or not view.roles:
            return await _reply(
                interaction,
                error_embed(
                    "Bitte Voice-Channel, Text-Channel und mindestens eine Rolle wählen."
                ),
            )
        old = db.get_voice_ping(interaction.guild_id) or {}
        db.set_voice_ping(
            interaction.guild_id,
            view.voice_id,
            view.text_id,
            view.roles,
            old.get("message"),
            int(old.get("cooldown") or 60),
        )
        await _reply(
            interaction,
            success_embed(
                "Voice-Ping gespeichert",
                (
                    f"**Voice:** <#{view.voice_id}>\n"
                    f"**Text:** <#{view.text_id}>\n"
                    f"**Rollen:** {' '.join(f'<@&{r}>' for r in view.roles)}\n"
                    "Spam-Schutz (Cooldown) bleibt aktiv."
                ),
            ),
            view=None,
        )


class VoicePingSetupView(discord.ui.View):
    def __init__(self, gid: int) -> None:
        super().__init__(timeout=1800)
        self.gid = gid
        cfg = db.get_voice_ping(gid) or {}
        self.voice_id = cfg.get("voice_channel_id")
        self.text_id = cfg.get("text_channel_id")
        self.roles = cfg.get("roles") or []
        self.add_item(VpVoiceSelect())
        self.add_item(VpTextSelect())
        self.add_item(VpRoleSelect())
        self.add_item(VpSaveButton())

    def build(self, note: str | None = None) -> discord.Embed:
        roles = (
            " ".join(f"<@&{r}>" for r in self.roles) if self.roles else "noch keine"
        )
        e = base_embed(
            "🔔 Voice-Rang-Ping einrichten",
            (
                "Wähle Voice-Channel, Text-Channel und Rollen und klicke "
                "**Speichern**.\nWird **dauerhaft** gespeichert.\n\n"
                f"**Voice:** {f'<#{self.voice_id}>' if self.voice_id else '–'}\n"
                f"**Text:** {f'<#{self.text_id}>' if self.text_id else '–'}\n"
                f"**Rollen:** {roles}"
            ),
            color=COLOR_MAIN,
        )
        if note:
            e.add_field(name="Status", value=note, inline=False)
        return e


# ======================================================================
#  Giveaway-Channel
# ======================================================================

class GiveawayChannelSelect(discord.ui.ChannelSelect):
    def __init__(self) -> None:
        super().__init__(
            channel_types=TEXT,
            placeholder="🎉 Giveaway-Channel wählen",
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        db.set_setting(interaction.guild_id, "giveaway_channel", self.values[0].id)
        view: GiveawaySetupView = self.view  # type: ignore[assignment]
        view.channel_id = self.values[0].id
        await _reply(
            interaction,
            view.build(note=f"✅ <#{self.values[0].id}> gespeichert"),
        )


class GiveawaySetupView(discord.ui.View):
    def __init__(self, gid: int) -> None:
        super().__init__(timeout=1800)
        self.gid = gid
        self.channel_id = int(db.get_setting(gid, "giveaway_channel") or 0) or None
        self.add_item(GiveawayChannelSelect())

    def build(self, note: str | None = None) -> discord.Embed:
        e = base_embed(
            "🎉 Giveaway einrichten",
            (
                "Wähle den Standard-Channel für Giveaways – wird **dauerhaft "
                "gespeichert**.\n\n"
                f"**Channel:** {f'<#{self.channel_id}>' if self.channel_id else 'noch nicht gesetzt'}\n\n"
                "Danach einfach `/giveaway prize:... duration:... winners:...` "
                "verwenden (der Channel ist dann vorausgewählt)."
            ),
            color=COLOR_MAIN,
        )
        if note:
            e.add_field(name="Status", value=note, inline=False)
        return e


# ======================================================================
#  Autorolle einrichten
# ======================================================================

class AutorollRoleSelect(discord.ui.RoleSelect):
    def __init__(self) -> None:
        super().__init__(
            placeholder="🔰 Rolle für neue Mitglieder wählen",
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: AutorollSetupView = self.view  # type: ignore[assignment]
        view.role_id = self.values[0].id
        await _reply(
            interaction,
            view.build(note=f"✅ {self.values[0].mention} ausgewählt"),
        )


class AutorollSaveButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="Speichern", emoji="✅",
            style=discord.ButtonStyle.primary, row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: AutorollSetupView = self.view  # type: ignore[assignment]
        if not view.role_id:
            return await _reply(
                interaction, error_embed("Bitte zuerst eine Rolle auswählen.")
            )
        db.set_setting(interaction.guild_id, "autoroll_role", view.role_id)
        role = (
            interaction.guild.get_role(view.role_id) if interaction.guild else None
        )
        await _reply(
            interaction,
            success_embed(
                "Autorolle gespeichert",
                (
                    f"Neue Mitglieder bekommen {role.mention if role else f'<@&{view.role_id}>'} "
                    "automatisch."
                ),
            ),
        )


class AutorollDisableButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="Deaktivieren", emoji="🗑️",
            style=discord.ButtonStyle.secondary, row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: AutorollSetupView = self.view  # type: ignore[assignment]
        db.delete_setting(interaction.guild_id, "autoroll_role")
        view.role_id = None
        await _reply(interaction, view.build(note="🗑️ Autorolle deaktiviert"))


class AutorollSetupView(discord.ui.View):
    def __init__(self, gid: int) -> None:
        super().__init__(timeout=1800)
        self.gid = gid
        self.role_id = int(db.get_setting(gid, "autoroll_role") or 0) or None
        self.add_item(AutorollRoleSelect())
        self.add_item(AutorollSaveButton())
        self.add_item(AutorollDisableButton())

    def build(self, note: str | None = None) -> discord.Embed:
        e = base_embed(
            "🔰 Autorolle einrichten",
            (
                "Neue Mitglieder bekommen die Rolle **automatisch**.\n"
                "Wähle eine Rolle und klicke auf **Speichern** – wird **dauerhaft "
                "gespeichert**.\n\n"
                f"**Rolle:** {f'<@&{self.role_id}>' if self.role_id else 'noch nicht gesetzt'}\n\n"
                "Die Rolle muss **über `@everyone`** liegen, sonst kann der Bot sie "
                "nicht vergeben."
            ),
            color=COLOR_MAIN,
        )
        if note:
            e.add_field(name="Status", value=note, inline=False)
        return e


# ======================================================================
#  Cog
# ======================================================================

class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # --------------------------------------------------------- /setup
    @app_commands.command(
        name="setup",
        description="🩵 Einrichtungsmenü für alle PrimeFFA-Systeme",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup(self, interaction: discord.Interaction) -> None:
        e = base_embed(
            "🩵 PrimeFFA Setup-Menü",
            (
                "Wähle unten aus, was du einrichten möchtest.\n"
                "**Alles wird sofort dauerhaft gespeichert** – auch nach "
                "Neustarts und Bot-Updates.\n\n" + "\n".join(status_lines(interaction.guild))
            ),
            color=COLOR_MAIN,
        )
        e.set_author(name=BRAND_NAME)
        e.add_field(
            name="Hinweis",
            value=(
                "Nur für Admins/Manager nutzbar. "
                "Das Menü bleibt hier stehen und funktioniert dauerhaft."
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=e, view=SetupMenuView())

    # ------------------------------------------------- Menü-Behandlung
    async def handle_menu(
        self, interaction: discord.Interaction, key: str
    ) -> None:
        if not is_admin(interaction.user):
            return await interaction.response.send_message(
                embed=error_embed(
                    "Dieses Menü ist nur für Admins/Manager nutzbar."
                ),
                ephemeral=True,
            )

        if key == "config":
            return await self.send_config(interaction)
        if key == "status":
            return await interaction.response.send_message(
                embed=status_embed(interaction.guild), ephemeral=True
            )

        builders = {
            "tickets": lambda: TicketsSetupView(interaction.guild_id),
            "welcome": lambda: MessageSetupView("welcome", interaction.guild_id),
            "leave": lambda: MessageSetupView("leave", interaction.guild_id),
            "counting": lambda: CountingSetupView(interaction.guild_id),
            "voiceping": lambda: VoicePingSetupView(interaction.guild_id),
            "giveaway": lambda: GiveawaySetupView(interaction.guild_id),
            "autoroll": lambda: AutorollSetupView(interaction.guild_id),
        }
        builder = builders.get(key)
        if builder is None:
            return await interaction.response.send_message(
                embed=error_embed("Unbekannte Auswahl."), ephemeral=True
            )
        view = builder()
        await interaction.response.send_message(
            embed=view.build(), view=view, ephemeral=True
        )

    # ----------------------------------------------------------- /config
    @app_commands.command(
        name="config", description="⚙️ Alle gespeicherten Einstellungen anzeigen"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def config(self, interaction: discord.Interaction) -> None:
        await self.send_config(interaction)

    async def send_config(self, interaction: discord.Interaction) -> None:
        rows = db.get_all_settings(interaction.guild_id)
        counting = db.get_counting(interaction.guild_id)
        voice = db.get_voice_ping(interaction.guild_id)

        if not rows and not counting and not voice:
            return await interaction.response.send_message(
                embed=info_embed(
                    "⚙️ Config",
                    "Es sind noch keine Einstellungen gespeichert.\n"
                    "Nutze `/setup`, um das Einrichtungsmenü zu öffnen.",
                ),
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)

        entries = [(r["key"], str(r["value"])) for r in rows]
        if counting and counting.get("channel_id"):
            entries.append(
                ("counting", f"channel={counting['channel_id']} record={counting['record']}")
            )
        if voice and voice.get("voice_channel_id"):
            entries.append(
                (
                    "voice_ping",
                    f"voice={voice['voice_channel_id']} text={voice['text_channel_id']} "
                    f"roles={voice['roles']} cooldown={voice['cooldown']}",
                )
            )

        chunks: list[list[tuple[str, str]]] = []
        current: list[tuple[str, str]] = []
        for key, value in entries:
            current.append((key, value))
            if len(current) == 10:
                chunks.append(current)
                current = []
        if current:
            chunks.append(current)

        for i, chunk in enumerate(chunks):
            e = base_embed(
                "⚙️ PrimeFFA Config"
                + (f" ({i + 1}/{len(chunks)})" if len(chunks) > 1 else ""),
                color=COLOR_LIGHT,
            )
            for key, value in chunk:
                if len(value) > 1000:
                    value = value[:1000] + "…"
                e.add_field(name=key, value=f"`{value}`", inline=False)
            await interaction.followup.send(embed=e, ephemeral=True)

    # -------------------------------------------------------- /bot-info
    @app_commands.command(name="bot-info", description="💻 Informationen über den Bot")
    async def botinfo(self, interaction: discord.Interaction) -> None:
        uptime = ts(self.bot.start_time, "R")
        members = sum(g.member_count for g in self.bot.guilds)
        e = base_embed(
            f"💻 {BRAND_NAME} Bot-Info",
            (
                f"**Name:** `{self.bot.user}`\n"
                f"**ID:** `{self.bot.user.id if self.bot.user else '-'}`\n"
                f"**Server:** `{len(self.bot.guilds)}`\n"
                f"**Mitglieder:** `{members}`\n"
                f"**Latenz:** `{round(self.bot.latency * 1000)} ms`\n"
                f"**Uptime:** {uptime}\n"
                f"**Python:** `{platform.python_version()}`\n"
                f"**discord.py:** `{discord.__version__}`\n"
                f"**Design:** 🩵 Babyblau (#89CFF0)"
            ),
            color=COLOR_DARK,
        )
        if self.bot.user:
            e.set_thumbnail(url=self.bot.user.display_avatar.url)
        e.add_field(
            name="Einrichtung",
            value="Öffne mit `/setup` das Einrichtungsmenü – alles speichert sich sofort.",
            inline=False,
        )
        await interaction.response.send_message(embed=e)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Admin(bot))
