"""Komplettes Ticketsystem von PrimeFFA.

Panel mit Dropdown, private Ticket-Channels, Claim, Close/Reopen/Delete,
Hinzufügen/Entfernen/Übertragen, Transkripte, Logs, Statistiken,
Kategorie-Support-Rollen und Schutz gegen doppelte Tickets.
"""

from __future__ import annotations

import html
import logging
import os
import re
import time

import discord
from discord import app_commands
from discord.ext import commands

import database as db
from config import (
    COLOR_DARK,
    COLOR_ERROR,
    COLOR_LIGHT,
    COLOR_MAIN,
    COLOR_SUCCESS,
    DEFAULT_TICKET_CATEGORY_NAME,
    TRANSCRIPT_LIMIT,
)
from utils import base_embed, error_embed, info_embed, success_embed, warn_embed

log = logging.getLogger("primeffa.tickets")

TRANSCRIPT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "transcripts")

PANEL_DESCRIPTION = (
    "Willkommen beim PrimeFFA Support!\n\n"
    "Wähle unten die passende Kategorie aus, um ein Ticket zu erstellen.\n\n"
    "Unser Team wird sich schnellstmöglich um dein Anliegen kümmern.\n\n"
    "Bitte erstelle nur Tickets, wenn du wirklich Hilfe benötigst."
)

TICKET_CATEGORIES: dict[str, dict] = {
    "support": {
        "label": "🛠️ Support",
        "name": "Support",
        "emoji": "🛠️",
        "description": "Allgemeine Fragen, Probleme & Hilfe",
        "welcome": (
            "Hallo {user} und willkommen im **PrimeFFA Support-Ticket**! 🩵\n\n"
            "Wir helfen dir bei:\n"
            "• Allgemeinen Fragen\n"
            "• Problemen\n"
            "• Fragen zum Server\n\n"
            "Beschreibe dein Anliegen möglichst genau – unser Team meldet sich "
            "schnellstmöglich bei dir."
        ),
    },
    "bug": {
        "label": "🐛 Bug Report",
        "name": "Bug-Report",
        "emoji": "🐛",
        "description": "Bugs und Fehler melden",
        "welcome": (
            "Hallo {user} und willkommen im **PrimeFFA Bug-Report-Ticket**! 🩵\n\n"
            "Bitte beschreibe den Fehler:\n"
            "• Was hast du getan?\n"
            "• Was ist passiert?\n"
            "• Was hättest du erwartet?\n\n"
            "Screenshots und Beweise kannst du direkt hier hochladen."
        ),
    },
    "report": {
        "label": "🚨 Report",
        "name": "Report",
        "emoji": "🚨",
        "description": "Spieler & Regelverstöße melden",
        "welcome": (
            "Hallo {user} und willkommen im **PrimeFFA Report-Ticket**! 🩵\n\n"
            "Bitte gib an:\n"
            "• **Spielername**\n"
            "• **Grund** (Regelverstoß)\n"
            "• **Beweise** (Screenshots/Clips)\n\n"
            "Dein Report wird vertraulich bearbeitet."
        ),
    },
    "staff": {
        "label": "🛡️ Staff Report",
        "name": "Staff-Report",
        "emoji": "🛡️",
        "description": "Beschwerden über Teammitglieder",
        "welcome": (
            "Hallo {user} und willkommen im **vertraulichen Staff-Report-Ticket**! 🩵\n\n"
            "Bitte gib an:\n"
            "• **Name des Teammitglieds**\n"
            "• **Grund der Beschwerde**\n"
            "• **Beweise**\n\n"
            "Dieses Ticket wird **ausschließlich** von berechtigten höheren "
            "Teammitgliedern eingesehen."
        ),
    },
    "giveaway": {
        "label": "🎉 Giveaway",
        "name": "Giveaway",
        "emoji": "🎉",
        "description": "Fragen zu Giveaways & Gewinnen",
        "welcome": (
            "Hallo {user} und willkommen im **PrimeFFA Giveaway-Ticket**! 🩵\n\n"
            "Wir helfen dir bei:\n"
            "• Fragen zu Giveaways\n"
            "• Problemen bei Gewinnspielen\n"
            "• Fragen zu Gewinnen und Preisen\n\n"
            "Beschreibe dein Problem kurz und genau."
        ),
    },
    "bewerbung": {
        "label": "📨 Bewerbung",
        "name": "Bewerbung",
        "emoji": "📨",
        "description": "Bewerbungen an das Team & Partner",
        "welcome": (
            "Hallo {user} und willkommen im **PrimeFFA Bewerbung-Ticket**! 🩵\n\n"
            "Bitte nenne:\n"
            "• Was du kannst und bisher gemacht hast\n"
            "• Was du willst – z. B. Rolle, Freizeit oder Partner\n"
            "• Links zu Projekten, Profilen oder Portfolio\n\n"
            "Unser Team kümmert sich um Bewerbungen. Beschreibe deine "
            "Bewerbung so gut wie möglich."
        ),
    },
    "iden": {
        "label": "💡 Iden",
        "name": "Iden",
        "emoji": "💡",
        "description": "Iden & Ideen – meldet alle Ideen für das Team",
        "welcome": (
            "Hallo {user} im **PrimeFFA Iden-Ticket** 🩵\n\n"
            "Beschreibe deine Iden/Ideen so genau wie möglich: Wann? Wo? "
            "Was wird daraus? Kontext und Hintergrund helfen, dass die "
            "Idee klarer klingt."
        ),
    },
}


def ticket_channel_name(
    user: discord.abc.User | None, key: str, *, closed: bool = False
) -> str:
    """Ticket-Channel-Name, z. B. 'Ticket JoeloKocht Support' bzw. 'Closed ...'."""
    label = TICKET_CATEGORIES.get(key, {}).get("name", key.title())
    raw = str(getattr(user, "display_name", None) or getattr(user, "name", "") or "")
    safe = re.sub(r"[^\w\- ]", "", raw, flags=re.UNICODE)
    safe = " ".join(safe.split())[:24].strip() or "User"
    return f"{'Closed ' if closed else 'Ticket '}{safe} {label}"[:100]


def open_channel_name(current: str, user: discord.abc.User | None, key: str) -> str:
    """Macht aus einem Closed-Namen wieder den offenen Namen."""
    if current.startswith("Closed "):
        return current[len("Closed "):] or ticket_channel_name(user, key)
    if current.startswith("Ticket "):
        return current
    return ticket_channel_name(user, key)


def closed_channel_name(current: str, user: discord.abc.User | None, key: str) -> str:
    """Macht aus einem offenen Namen den Closed-Namen (Kategorie bleibt drin)."""
    if current.startswith("Closed "):
        return current
    if current.startswith("Ticket "):
        return f"Closed {current}"[:100]
    return ticket_channel_name(user, key, closed=True)


def is_staff(member: discord.Member, category: str | None = None) -> bool:
    """Prüft, ob Mitglied Ticket-Rechte hat (Manage Guild, Staff- oder Kategorie-Rolle)."""
    if member.guild_permissions.manage_guild or member.guild_permissions.administrator:
        return True
    role_ids: list[int] = []
    staff = db.get_setting(member.guild.id, "ticket_staff_role")
    if staff:
        try:
            role_ids.append(int(staff))
        except ValueError:
            pass
    if category:
        cat_role = db.get_setting(member.guild.id, f"ticket_role_{category}")
        if cat_role:
            try:
                role_ids.append(int(cat_role))
            except ValueError:
                pass
    member_roles = {r.id for r in member.roles}
    return any(rid in member_roles for rid in role_ids)


# ============================================================ Panel (Dropdown)

class TicketPanelSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(
                label=data["label"],
                value=key,
                description=data["description"],
                emoji=data["emoji"],
            )
            for key, data in TICKET_CATEGORIES.items()
        ]
        super().__init__(
            custom_id="primeffa_ticket_panel",
            placeholder="🩵 Wähle eine Kategorie aus",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = interaction.client.get_cog("Tickets")
        if cog is None:
            return await interaction.response.send_message(
                embed=error_embed("Ticket-System nicht geladen."), ephemeral=True
            )
        if not self.values:
            return await interaction.response.send_message(
                embed=error_embed("Bitte wähle eine Kategorie aus."), ephemeral=True
            )
        await cog.handle_panel_select(interaction, self.values[0])


class TicketPanelView(discord.ui.View):
    """Persistente Panel-View (überlebt Neustarts)."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(TicketPanelSelect())


# ====================================================== Ticket-Kontroll-Buttons

class _TicketButton(discord.ui.Button):
    action = ""

    def __init__(self, label: str, emoji: str, style: discord.ButtonStyle, row: int):
        super().__init__(
            custom_id=f"ticket_{self.action}",
            label=label,
            emoji=emoji,
            style=style,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = interaction.client.get_cog("Tickets")
        if cog is None:
            return await interaction.response.send_message(
                embed=error_embed("Ticket-System nicht geladen."), ephemeral=True
            )
        await cog.handle_button(interaction, self.action)


class ClaimButton(_TicketButton):
    action = "claim"

    def __init__(self) -> None:
        super().__init__("Claimen", "🙋", discord.ButtonStyle.secondary, 1)


class AddButton(_TicketButton):
    action = "add"

    def __init__(self) -> None:
        super().__init__("Hinzufügen", "➕", discord.ButtonStyle.secondary, 1)


class RemoveButton(_TicketButton):
    action = "remove"

    def __init__(self) -> None:
        super().__init__("Entfernen", "➖", discord.ButtonStyle.secondary, 1)


class TransferButton(_TicketButton):
    action = "transfer"

    def __init__(self) -> None:
        super().__init__("Übertragen", "🔁", discord.ButtonStyle.secondary, 1)


class TranscriptButton(_TicketButton):
    action = "transcript"

    def __init__(self) -> None:
        super().__init__("Transkript", "📄", discord.ButtonStyle.secondary, 2)


class CloseButton(_TicketButton):
    action = "close"

    def __init__(self) -> None:
        super().__init__("Schließen", "🔒", discord.ButtonStyle.danger, 0)


class ReopenButton(_TicketButton):
    action = "reopen"

    def __init__(self) -> None:
        super().__init__("Öffnen", "🔓", discord.ButtonStyle.success, 3)


class DeleteButton(_TicketButton):
    action = "delete"

    def __init__(self) -> None:
        super().__init__("Löschen", "🗑️", discord.ButtonStyle.danger, 3)


class TicketControlView(discord.ui.View):
    """Persistente View: Schließen, Hinzufügen, Entfernen, Claimen."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(CloseButton())
        self.add_item(AddButton())
        self.add_item(RemoveButton())
        self.add_item(ClaimButton())


class LegacyTicketControlView(discord.ui.View):
    """Hält die alten Buttons (Übertragen, Transkript, Öffnen, Löschen) auf
    bestehenden Ticket-Nachrichten weiterhin bedienbar."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(TransferButton())
        self.add_item(TranscriptButton())
        self.add_item(ReopenButton())
        self.add_item(DeleteButton())


# ===================================================== Temporäre Helfer-Views

class MemberSelect(discord.ui.UserSelect):
    def __init__(self, action: str, cog: "Tickets", ticket: dict):
        super().__init__(
            placeholder="👤 Mitglied auswählen…",
            min_values=1,
            max_values=10,
        )
        self.action = action
        self.cog = cog
        self.ticket = ticket

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.cog.apply_member_action(
            interaction, self.action, self.ticket, self.values
        )


class MemberActionView(discord.ui.View):
    def __init__(self, action: str, cog: "Tickets", ticket: dict):
        super().__init__(timeout=300)
        self.add_item(MemberSelect(action, cog, ticket))


class DeleteConfirmButton(discord.ui.Button):
    def __init__(self, cog: "Tickets", ticket: dict):
        super().__init__(
            custom_id="ticket_delete_confirm",
            label="Endgültig löschen",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
        )
        self.cog = cog
        self.ticket = ticket

    async def callback(self, interaction: discord.Interaction) -> None:
        await self.cog.perform_delete(interaction, self.ticket)


class DeleteConfirmView(discord.ui.View):
    def __init__(self, cog: "Tickets", ticket: dict):
        super().__init__(timeout=120)
        self.add_item(DeleteConfirmButton(cog, ticket))


class CloseModal(discord.ui.Modal):
    """Optionaler Grund – wird genutzt, wenn ein Ticket per Modal geschlossen wird."""

    reason = discord.ui.TextInput(
        label="Grund (optional)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
        placeholder="Warum wird das Ticket geschlossen?",
    )

    def __init__(self, cog: "Tickets", ticket: dict):
        super().__init__(title="Ticket schließen")
        self.cog = cog
        self.ticket = ticket

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.cog.perform_close(
            interaction, self.ticket, str(self.reason).strip() or "Kein Grund angegeben"
        )


# ====================================================================== Cog

class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------ Helper
    def _log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        cid = db.get_int(guild.id, "ticket_log_channel", 0)
        if not cid:
            return None
        ch = guild.get_channel(cid)
        return ch if isinstance(ch, discord.TextChannel) else None

    async def log_action(
        self,
        guild: discord.Guild,
        title: str,
        description: str,
        user: discord.abc.User,
        color: int = COLOR_MAIN,
        file: discord.File | None = None,
    ) -> None:
        channel = self._log_channel(guild)
        if channel is None:
            return
        e = base_embed(f"🎫 {title}", description, color=color)
        e.set_author(name=f"{user} • {user.id}", icon_url=user.display_avatar.url)
        e.timestamp = discord.utils.utcnow()
        try:
            await channel.send(embed=e, file=file)
        except discord.HTTPException as exc:
            log.warning("Ticket-Log fehlgeschlagen: %s", exc)

    def _category_role(self, guild: discord.Guild, key: str) -> discord.Role | None:
        rid = db.get_int(guild.id, f"ticket_role_{key}", 0)
        return guild.get_role(rid) if rid else None

    def _staff_role(self, guild: discord.Guild) -> discord.Role | None:
        rid = db.get_int(guild.id, "ticket_staff_role", 0)
        return guild.get_role(rid) if rid else None

    async def _ticket_category(self, guild: discord.Guild) -> discord.CategoryChannel:
        cid = db.get_int(guild.id, "ticket_category_id", 0)
        cat = guild.get_channel(cid) if cid else None
        if isinstance(cat, discord.CategoryChannel):
            return cat
        for c in guild.categories:
            if c.name == DEFAULT_TICKET_CATEGORY_NAME:
                db.set_setting(guild.id, "ticket_category_id", c.id)
                return c
        cat = await guild.create_category(
            DEFAULT_TICKET_CATEGORY_NAME,
            reason="PrimeFFA Ticketsystem",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True, manage_channels=True, send_messages=True
                ),
            },
        )
        db.set_setting(guild.id, "ticket_category_id", cat.id)
        return cat

    async def _closed_category(
        self, guild: discord.Guild, key: str
    ) -> discord.CategoryChannel:
        """Eigene Kategorie für geschlossene Tickets dieser Ticket-Kategorie,
        z. B. 'Geschlossen • Support'."""
        label = TICKET_CATEGORIES.get(key, {}).get("name", str(key).title())
        name = f"Geschlossen • {label}"
        setting = f"ticket_closed_category_{key}"

        cid = db.get_int(guild.id, setting, 0)
        cat = guild.get_channel(cid) if cid else None
        if isinstance(cat, discord.CategoryChannel):
            return cat
        for c in guild.categories:
            if c.name == name:
                db.set_setting(guild.id, setting, c.id)
                return c
        cat = await guild.create_category(
            name,
            reason="PrimeFFA geschlossene Tickets",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True, manage_channels=True, send_messages=True
                ),
            },
        )
        db.set_setting(guild.id, setting, cat.id)
        return cat

    def _ticket_channel(self, interaction: discord.Interaction) -> tuple[discord.TextChannel, dict] | None:
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            return None
        ticket = db.get_ticket_by_channel(ch.id)
        if not ticket:
            return None
        return ch, ticket

    # ------------------------------------------------------- Panel & Erstellung
    async def handle_panel_select(
        self, interaction: discord.Interaction, key: str
    ) -> None:
        if key not in TICKET_CATEGORIES:
            return await interaction.response.send_message(
                embed=error_embed("Unbekannte Kategorie."), ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if guild is None:
            return await interaction.followup.send(
                embed=error_embed("Nur auf einem Server nutzbar."), ephemeral=True
            )
        user = interaction.user
        assert isinstance(user, discord.Member)

        # Schutz gegen mehrfache Tickets
        existing = db.get_open_ticket(guild.id, user.id)
        if existing:
            ch = guild.get_channel(existing["channel_id"])
            if ch is not None:
                return await interaction.followup.send(
                    embed=error_embed(
                        f"Du hast bereits ein offenes Ticket: {ch.mention}\n"
                        "Bitte nutze dieses zuerst oder schließe es."
                    ),
                    ephemeral=True,
                )
            db.close_ticket(existing["channel_id"], "Kanal nicht mehr vorhanden")

        cat_data = TICKET_CATEGORIES[key]
        category = await self._ticket_category(guild)
        number = db.next_ticket_number(guild.id)
        channel_name = ticket_channel_name(user, key)

        overwrites: dict[
            discord.abc.Snowflake, discord.PermissionOverwrite
        ] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, attach_files=True,
                embed_links=True, read_message_history=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True,
                manage_messages=True, embed_links=True, attach_files=True,
                read_message_history=True,
            ),
        }
        staff = self._staff_role(guild)
        if staff:
            overwrites[staff] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, attach_files=True,
                embed_links=True, read_message_history=True,
            )
        cat_role = self._category_role(guild, key)
        if cat_role and cat_role != staff:
            overwrites[cat_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, attach_files=True,
                embed_links=True, read_message_history=True,
            )

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                reason=f"Ticket #{number} von {user} ({cat_data['name']})",
                topic=f"Ticket #{number} | {cat_data['label']} | Ersteller: {user.id}",
            )
        except discord.HTTPException as exc:
            log.exception("Ticket-Erstellung fehlgeschlagen")
            return await interaction.followup.send(
                embed=error_embed(f"Ticket konnte nicht erstellt werden:\n`{exc}`"),
                ephemeral=True,
            )

        db.add_ticket(guild.id, channel.id, user.id, key, number)

        e = base_embed(
            f"🎫 Ticket #{number} – {cat_data['label']}",
            cat_data["welcome"].format(user=user.mention),
            color=COLOR_MAIN,
        )
        e.add_field(name="Kategorie", value=cat_data["label"], inline=True)
        e.add_field(name="Ersteller", value=user.mention, inline=True)
        e.add_field(name="Status", value="🟢 Offen", inline=True)
        e.add_field(name="Ticket-Nr.", value=f"#{number}", inline=True)
        e.set_thumbnail(url=user.display_avatar.url)
        e.timestamp = discord.utils.utcnow()
        await channel.send(
            content=f"{user.mention}" + (
                f" {staff.mention}" if staff else ""
            ),
            embed=e,
            view=TicketControlView(),
        )

        await self.log_action(
            guild,
            "Ticket erstellt",
            (
                f"**Kanal:** {channel.mention}\n"
                f"**Nr.:** #{number}\n"
                f"**Kategorie:** {cat_data['label']}\n"
                f"**Ersteller:** {user.mention}"
            ),
            user,
            color=COLOR_SUCCESS,
        )

        await interaction.followup.send(
            embed=success_embed(
                "Ticket erstellt",
                f"Dein Ticket wurde erstellt: {channel.mention}",
            ),
            ephemeral=True,
        )

    # ------------------------------------------------------------- Buttons
    async def handle_button(self, interaction: discord.Interaction, action: str) -> None:
        resolved = self._ticket_channel(interaction)
        if resolved is None:
            return await interaction.response.send_message(
                embed=error_embed("Hier existiert kein Ticket."), ephemeral=True
            )
        channel, ticket = resolved
        user = interaction.user
        assert isinstance(user, discord.Member)

        owner_id = int(ticket["owner_id"])
        staff = is_staff(user, ticket["category"])
        is_owner = user.id == owner_id
        claimed_by = ticket.get("claimed_by")

        if action == "transcript":
            if not (staff or is_owner):
                return await interaction.response.send_message(
                    embed=error_embed("Keine Berechtigung."), ephemeral=True
                )
            await interaction.response.defer(ephemeral=True)
            path = await self.make_transcript(channel, ticket)
            if path is None:
                return await interaction.followup.send(
                    embed=error_embed("Transkript konnte nicht erstellt werden."),
                    ephemeral=True,
                )
            await interaction.followup.send(
                embed=success_embed(
                    "Transkript erstellt", f"Ticket #{ticket['number']}"
                ),
                file=discord.File(path),
                ephemeral=True,
            )
            return

        if action == "claim":
            if not staff:
                return await interaction.response.send_message(
                    embed=error_embed("Nur Teammitglieder können Tickets beanspruchen."),
                    ephemeral=True,
                )
            if ticket["status"] != "open":
                return await interaction.response.send_message(
                    embed=error_embed("Dieses Ticket ist geschlossen."), ephemeral=True
                )
            if claimed_by and int(claimed_by) != user.id:
                holder = channel.guild.get_member(int(claimed_by))
                return await interaction.response.send_message(
                    embed=error_embed(
                        f"Das Ticket ist bereits von "
                        f"{holder.mention if holder else f'<@{claimed_by}>'} beansprucht."
                    ),
                    ephemeral=True,
                )
            db.set_ticket_claimed(channel.id, user.id)
            await interaction.response.send_message(
                embed=success_embed(
                    "Ticket beansprucht",
                    f"{user.mention} hat das Ticket übernommen.",
                )
            )
            await self.log_action(
                interaction.guild,
                "Ticket beansprucht",
                f"**Kanal:** {channel.mention}\n**Durch:** {user.mention}",
                user,
                color=COLOR_DARK,
            )
            return

        if action == "close":
            if not (staff or is_owner):
                return await interaction.response.send_message(
                    embed=error_embed("Keine Berechtigung."), ephemeral=True
                )
            if ticket["status"] != "open":
                return await interaction.response.send_message(
                    embed=error_embed("Das Ticket ist bereits geschlossen."),
                    ephemeral=True,
                )
            # Direkt schließen – kein Rückfrage-Modal
            await self.perform_close(
                interaction, ticket, "Direkt geschlossen", channel=channel
            )
            return

        if action == "reopen":
            if not (staff or is_owner):
                return await interaction.response.send_message(
                    embed=error_embed("Keine Berechtigung."), ephemeral=True
                )
            if ticket["status"] == "open":
                return await interaction.response.send_message(
                    embed=error_embed("Das Ticket ist bereits offen."), ephemeral=True
                )
            await self.perform_reopen(interaction, channel, ticket)
            return

        if action == "delete":
            if not (staff or is_owner):
                return await interaction.response.send_message(
                    embed=error_embed("Keine Berechtigung."), ephemeral=True
                )
            await interaction.response.send_message(
                embed=warn_embed(
                    "Ticket löschen?",
                    "Das Ticket wird **dauerhaft** mit allen Daten gelöscht.\n"
                    "Ein Transkript wird vorher erstellt und geloggt.",
                ),
                view=DeleteConfirmView(self, ticket),
                ephemeral=True,
            )
            return

        if action in ("add", "remove", "transfer"):
            if not staff:
                return await interaction.response.send_message(
                    embed=error_embed("Nur Teammitglieder dürfen das tun."),
                    ephemeral=True,
                )
            labels = {
                "add": ("➕ Mitglied hinzufügen", "Wähle die Mitglieder aus."),
                "remove": ("➖ Mitglied entfernen", "Wähle die Mitglieder aus."),
                "transfer": ("🔁 Ticket übertragen",
                             "Wähle das Teammitglied aus, das das Ticket übernimmt."),
            }
            title, desc = labels[action]
            await interaction.response.send_message(
                embed=info_embed(title, desc),
                view=MemberActionView(action, self, ticket),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=error_embed("Unbekannte Aktion."), ephemeral=True
        )

    # ------------------------------------------------- Mitglieder-Aktionen
    async def apply_member_action(
        self,
        interaction: discord.Interaction,
        action: str,
        ticket: dict,
        values: list[discord.User],
    ) -> None:
        resolved = self._ticket_channel(interaction)
        if resolved is None:
            return await interaction.response.send_message(
                embed=error_embed("Ticket nicht mehr vorhanden."), ephemeral=True
            )
        channel, _ = resolved
        guild = interaction.guild
        assert guild is not None

        # Sofort antworten – Mitglieder suchen + Rechte setzen dauert zu lange
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        done: list[str] = []
        for value in values:
            member = guild.get_member(value.id)
            if member is None:
                try:
                    member = await guild.fetch_member(value.id)
                except discord.HTTPException:
                    continue
            if member.bot:
                continue
            if action == "remove" and member.id == int(ticket["owner_id"]):
                continue
            try:
                if action in ("add", "transfer"):
                    await channel.set_permissions(
                        member,
                        view_channel=True,
                        send_messages=True,
                        attach_files=True,
                        embed_links=True,
                        read_message_history=True,
                        reason=f"Ticket-Aktion durch {interaction.user}",
                    )
                else:
                    await channel.set_permissions(
                        member,
                        overwrite=None,
                        reason=f"Ticket-Aktion durch {interaction.user}",
                    )
                done.append(member.mention)
            except discord.HTTPException:
                continue

        if action == "transfer":
            target = values[0]
            db.set_ticket_claimed(channel.id, target.id)
            embed = success_embed(
                "Ticket übertragen", f"Das Ticket liegt jetzt bei {target.mention}."
            )
            await self.log_action(
                guild,
                "Ticket übertragen",
                f"**Kanal:** {channel.mention}\n**An:** {target.mention}",
                interaction.user,
                color=COLOR_DARK,
            )
        elif action == "add":
            embed = success_embed(
                "Hinzugefügt", f"Hinzugefügt: {', '.join(done) or '–'}"
            )
        else:
            embed = success_embed(
                "Entfernt", f"Entfernt: {', '.join(done) or '–'}"
            )

        await interaction.followup.edit_message(
            interaction.message.id, embed=embed, view=None
        )

    # ------------------------------------------------------- Close/Reopen/Delete
    async def perform_close(
        self,
        interaction: discord.Interaction,
        ticket: dict,
        reason: str,
        channel: discord.TextChannel | None = None,
    ) -> None:
        if channel is None:
            resolved = self._ticket_channel(interaction)
            if resolved is None:
                return await interaction.response.send_message(
                    embed=error_embed("Ticket nicht mehr vorhanden."), ephemeral=True
                )
            channel, ticket = resolved

        # Sofort antworten (Discord gibt nur 3 Sekunden), danach lange Arbeit
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        guild = channel.guild
        owner = guild.get_member(int(ticket["owner_id"]))

        path = await self.make_transcript(channel, ticket)
        db.close_ticket(channel.id, reason)
        db.set_ticket_claimed(channel.id, ticket.get("claimed_by"))

        # Owner ausblenden (Kanal bleibt für Reopen erhalten)
        if owner:
            try:
                await channel.set_permissions(
                    owner, view_channel=False, reason="Ticket geschlossen"
                )
            except discord.HTTPException:
                pass
        # Kanal bekommt den Namen "Closed <Name> <Kategorie>" und wandert
        # in die eigene geschlossene Kategorie dieser Ticket-Kategorie
        try:
            closed_cat = await self._closed_category(guild, ticket["category"])
        except discord.HTTPException:
            closed_cat = None
        new_name = closed_channel_name(
            channel.name, owner or interaction.user, ticket["category"]
        )
        try:
            await channel.edit(
                name=new_name,
                category=closed_cat,
                reason="Ticket geschlossen",
            )
        except discord.HTTPException:
            pass

        e = base_embed(
            "🔒 Ticket geschlossen",
            (
                f"Dieses Ticket wurde geschlossen.\n\n"
                f"**Grund:** {reason}\n"
                f"**Geschlossen von:** {interaction.user.mention}\n\n"
                "Ein Teammitglied kann es mit dem **🔓 Öffnen**-Button wieder "
                "öffnen."
            ),
            color=COLOR_DARK,
        )
        await channel.send(
            content=owner.mention if owner else None, embed=e, view=TicketControlView()
        )

        await self.log_action(
            guild,
            "Ticket geschlossen",
            (
                f"**Kanal:** #{channel.name}\n"
                f"**Nr.:** #{ticket['number']}\n"
                f"**Grund:** {reason}\n"
                f"**Durch:** {interaction.user.mention}"
            ),
            interaction.user,
            color=COLOR_DARK,
        )

        if path and os.path.exists(path):
            try:
                await self.log_action(
                    guild,
                    "Transkript",
                    f"Ticket #{ticket['number']} – `{os.path.basename(path)}`",
                    interaction.user,
                    color=COLOR_LIGHT,
                    file=discord.File(path),
                )
            except discord.HTTPException:
                pass

        await interaction.followup.send(
            embed=success_embed(
                "Ticket geschlossen", f"Ticket #{ticket['number']} wurde geschlossen."
            ),
            ephemeral=True,
        )

    async def perform_reopen(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        ticket: dict,
    ) -> None:
        # Sofort antworten – Rechte setzen + Umbenennen dauert zu lange für 3s
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        guild = channel.guild
        owner = guild.get_member(int(ticket["owner_id"]))
        staff = self._staff_role(guild)
        cat_role = self._category_role(guild, ticket["category"])

        if owner:
            try:
                await channel.set_permissions(
                    owner,
                    view_channel=True,
                    send_messages=True,
                    attach_files=True,
                    embed_links=True,
                    read_message_history=True,
                    reason="Ticket wieder geöffnet",
                )
            except discord.HTTPException:
                pass
        for role in (staff, cat_role):
            if role:
                try:
                    await channel.set_permissions(
                        role,
                        view_channel=True,
                        send_messages=True,
                        attach_files=True,
                        embed_links=True,
                        read_message_history=True,
                        reason="Ticket wieder geöffnet",
                    )
                except discord.HTTPException:
                    pass

        db.reopen_ticket(channel.id)
        # Zurück in die normale Ticket-Kategorie + offener Name
        try:
            main_cat = await self._ticket_category(guild)
        except discord.HTTPException:
            main_cat = None
        new_name = open_channel_name(
            channel.name, owner or interaction.user, ticket["category"]
        )
        try:
            await channel.edit(
                name=new_name,
                category=main_cat,
                reason="Ticket wieder geöffnet",
            )
        except discord.HTTPException:
            pass

        e = base_embed(
            "🔓 Ticket wieder geöffnet",
            f"Durch {interaction.user.mention} – das Ticket ist wieder aktiv.",
            color=COLOR_SUCCESS,
        )
        await channel.send(embed=e, view=TicketControlView())
        await self.log_action(
            guild,
            "Ticket wieder geöffnet",
            f"**Kanal:** {channel.mention}\n**Durch:** {interaction.user.mention}",
            interaction.user,
            color=COLOR_SUCCESS,
        )
        await interaction.followup.send(
            embed=success_embed("Wieder geöffnet", f"{channel.mention} ist offen."),
            ephemeral=True,
        )

    async def perform_delete(
        self, interaction: discord.Interaction, ticket: dict
    ) -> None:
        resolved = self._ticket_channel(interaction)
        if resolved is None:
            return await interaction.response.send_message(
                embed=error_embed("Ticket nicht mehr vorhanden."), ephemeral=True
            )
        channel, ticket = resolved
        guild = channel.guild

        await interaction.response.defer(ephemeral=True)
        path = await self.make_transcript(channel, ticket)

        await self.log_action(
            guild,
            "Ticket gelöscht",
            (
                f"**Kanal:** #{channel.name}\n"
                f"**Nr.:** #{ticket['number']}\n"
                f"**Ersteller:** <@{ticket['owner_id']}>\n"
                f"**Durch:** {interaction.user.mention}"
            ),
            interaction.user,
            color=COLOR_ERROR,
        )
        if path and os.path.exists(path):
            try:
                await self.log_action(
                    guild,
                    "Transkript (gelöschtes Ticket)",
                    f"Ticket #{ticket['number']}",
                    interaction.user,
                    color=COLOR_LIGHT,
                    file=discord.File(path),
                )
            except discord.HTTPException:
                pass

        db.delete_ticket_record(channel.id)
        try:
            await channel.delete(reason=f"Ticket gelöscht von {interaction.user}")
        except discord.HTTPException:
            return await interaction.followup.send(
                embed=error_embed("Kanal konnte nicht gelöscht werden."),
                ephemeral=True,
            )
        await interaction.followup.send(
            embed=success_embed("Gelöscht", "Das Ticket wurde gelöscht."),
            ephemeral=True,
        )

    # ---------------------------------------------------------- Transkript
    async def make_transcript(
        self, channel: discord.TextChannel, ticket: dict
    ) -> str | None:
        try:
            messages: list[discord.Message] = []
            async for msg in channel.history(limit=TRANSCRIPT_LIMIT, oldest_first=True):
                messages.append(msg)

            rows = []
            for m in messages:
                avatar = m.author.display_avatar.url
                time_str = m.created_at.strftime("%d.%m.%Y %H:%M")
                content = html.escape(m.content or "")
                if m.attachments:
                    links = ", ".join(
                        html.escape(a.url) for a in m.attachments[:5]
                    )
                    content += f"<div class='att'>📎 {links}</div>"
                rows.append(
                    "<div class='msg'>"
                    f"<img src='{avatar}' class='avatar'>"
                    "<div class='body'>"
                    f"<span class='name'>{html.escape(m.author.display_name)}</span>"
                    f"<span class='time'>{time_str}</span>"
                    f"<div class='text'>{content or '<em>–</em>'}</div>"
                    "</div></div>"
                )

            cat = TICKET_CATEGORIES.get(ticket["category"], {})
            doc = f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<title>PrimeFFA Ticket #{ticket['number']}</title>
<style>
 body{{background:#eef8fd;font-family:Segoe UI,Arial,sans-serif;margin:0;padding:24px;color:#2c3e50}}
 .head{{background:linear-gradient(90deg,#89CFF0,#BFEFFF);border-radius:14px;padding:18px 22px;box-shadow:0 4px 14px rgba(93,173,226,.35)}}
 .head h1{{margin:0;color:#fff;font-size:22px}}
 .head p{{margin:6px 0 0;color:#ffffffee;font-size:14px}}
 .msg{{display:flex;gap:10px;margin-top:12px;background:#fff;border-left:4px solid #89CFF0;border-radius:10px;padding:10px 12px}}
 .avatar{{width:40px;height:40px;border-radius:50%;border:2px solid #BFEFFF}}
 .name{{font-weight:700;color:#5DADE2;margin-right:8px}}
 .time{{font-size:11px;color:#95a5a6}}
 .text{{margin-top:4px;white-space:pre-wrap;word-break:break-word}}
 .att{{color:#5DADE2;font-size:12px;margin-top:4px}}
 .foot{{margin-top:20px;text-align:center;color:#7f8c8d;font-size:12px}}
</style></head><body>
<div class="head">
 <h1>🩵 PrimeFFA Ticket #{ticket['number']}</h1>
 <p>Kategorie: {cat.get('name', ticket['category'])} |
    Ersteller: &lt;@{ticket['owner_id']}&gt; |
    Status: {ticket['status']} |
    Erstellt: {time.strftime('%d.%m.%Y %H:%M', time.localtime(ticket['created_at']))}</p>
</div>
{''.join(rows) if rows else '<p>Keine Nachrichten.</p>'}
<div class="foot">PrimeFFA • Transkript erstellt am {time.strftime('%d.%m.%Y %H:%M')}</div>
</body></html>"""

            out_dir = os.path.join(TRANSCRIPT_DIR, str(channel.guild.id))
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(
                out_dir,
                f"ticket-{ticket['number']}-{int(time.time())}.html",
            )
            with open(path, "w", encoding="utf-8") as f:
                f.write(doc)
            db.set_ticket_transcript(channel.id, path)
            return path
        except Exception:
            log.exception("Transkript-Erstellung fehlgeschlagen")
            return None

    # ============================================================ Commands

    @app_commands.command(
        name="ticket-setup", description="🎫 Ticket-Panel erstellen"
    )
    @app_commands.describe(
        staff_role="Rolle, die Tickets verwalten darf",
        log_channel="Channel für Ticket-Logs",
        panel_channel="Channel für das Panel (Standard: aktueller)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        staff_role: discord.Role = None,
        log_channel: discord.TextChannel = None,
        panel_channel: discord.TextChannel = None,
    ) -> None:
        if staff_role:
            db.set_setting(interaction.guild_id, "ticket_staff_role", staff_role.id)
        if log_channel:
            db.set_setting(interaction.guild_id, "ticket_log_channel", log_channel.id)
        target = panel_channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            return await interaction.response.send_message(
                embed=error_embed("Bitte wähle einen gültigen Text-Channel."),
                ephemeral=True,
            )

        err = await self.send_panel(target)
        if err:
            return await interaction.response.send_message(
                embed=error_embed(err), ephemeral=True
            )

        db.set_setting(interaction.guild_id, "ticket_panel_channel", target.id)
        info = [
            f"**Panel:** {target.mention}",
            f"**Staff-Rolle:** {staff_role.mention if staff_role else 'Standard (Manage Server)'}",
            f"**Log-Channel:** {log_channel.mention if log_channel else 'nicht gesetzt'}",
            "",
            "Kategorie-Rollen mit `/ticket-roles` festlegen.",
        ]
        await interaction.response.send_message(
            embed=success_embed("Ticket-Panel erstellt", "\n".join(info)),
            ephemeral=True,
        )

    async def send_panel(self, target: discord.TextChannel) -> str | None:
        """Sendet das Ticket-Panel. None = OK, sonst Fehlermeldung."""
        e = base_embed("🩵 PrimeFFA Support", PANEL_DESCRIPTION, color=COLOR_MAIN)
        e.set_author(name="PrimeFFA • Ticket-System")
        e.add_field(
            name="Kategorien",
            value="\n".join(
                f"{c['emoji']} {c['label']} – {c['description']}"
                for c in TICKET_CATEGORIES.values()
            ),
            inline=False,
        )
        e.set_footer(text="PrimeFFA")
        try:
            await target.send(embed=e, view=TicketPanelView())
        except discord.HTTPException as exc:
            return f"Panel konnte nicht gesendet werden: `{exc}`"
        return None

    @app_commands.command(
        name="ticket-logs", description="🎫 Ticket-Log-Channel festlegen"
    )
    @app_commands.describe(channel="Log-Channel (leer = deaktivieren)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_logs(
        self, interaction: discord.Interaction, channel: discord.TextChannel = None
    ) -> None:
        if channel:
            db.set_setting(interaction.guild_id, "ticket_log_channel", channel.id)
            msg = f"Logs werden jetzt an {channel.mention} gesendet."
        else:
            db.delete_setting(interaction.guild_id, "ticket_log_channel")
            msg = "Ticket-Logs sind deaktiviert."
        await interaction.response.send_message(
            embed=success_embed("Ticket-Logs", msg), ephemeral=True
        )

    @app_commands.command(
        name="ticket-roles",
        description="🎫 Support-Rolle für eine Ticket-Kategorie festlegen",
    )
    @app_commands.describe(
        category="Ticket-Kategorie", role="Rolle, die diese Tickets sehen darf"
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name=c["label"], value=k)
            for k, c in TICKET_CATEGORIES.items()
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_roles(
        self,
        interaction: discord.Interaction,
        category: app_commands.Choice[str],
        role: discord.Role,
    ) -> None:
        db.set_setting(
            interaction.guild_id, f"ticket_role_{category.value}", role.id
        )
        await interaction.response.send_message(
            embed=success_embed(
                "Kategorie-Rolle gesetzt",
                f"{TICKET_CATEGORIES[category.value]['label']} → {role.mention}",
            ),
            ephemeral=True,
        )

    @app_commands.command(
        name="ticket-closed", description="🎫 Geschlossene Tickets ansehen"
    )
    @app_commands.describe(number="Ticket-Nummer für Details + Transkript")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_closed(
        self, interaction: discord.Interaction, number: int = None
    ) -> None:
        if number:
            ticket = db.get_ticket_by_number(interaction.guild_id, number)
            if not ticket or ticket["status"] != "closed":
                return await interaction.response.send_message(
                    embed=error_embed(f"Kein geschlossenes Ticket mit der Nr. #{number}."),
                    ephemeral=True,
                )
            cat = TICKET_CATEGORIES.get(ticket["category"], {})
            e = base_embed(
                f"🎫 Geschlossenes Ticket #{number}",
                (
                    f"**Kategorie:** {cat.get('label', ticket['category'])}\n"
                    f"**Ersteller:** <@{ticket['owner_id']}>\n"
                    f"**Geschlossen am:** "
                    f"<t:{int(ticket['closed_at'] or 0)}:f>\n"
                    f"**Grund:** {ticket['close_reason'] or '–'}\n"
                    f"**Transkript:** "
                    f"{'gespeichert ✅' if ticket['transcript'] else '–'}"
                ),
                color=COLOR_DARK,
            )
            return await interaction.response.send_message(embed=e, ephemeral=True)

        rows = db.list_closed_tickets(interaction.guild_id, 10)
        if not rows:
            return await interaction.response.send_message(
                embed=info_embed(
                    "🎫 Geschlossene Tickets", "Es gibt noch keine geschlossenen Tickets."
                ),
                ephemeral=True,
            )
        lines = []
        for t in rows:
            cat = TICKET_CATEGORIES.get(t["category"], {})
            when = f"<t:{int(t['closed_at'] or 0)}:R>"
            lines.append(
                f"**#{t['number']}** {cat.get('label', t['category'])} • "
                f"<@{t['owner_id']}> • {when}"
            )
        e = base_embed(
            "🎫 Letzte geschlossene Tickets",
            "\n".join(lines) + "\n\nDetails: `/ticket-closed number:`",
            color=COLOR_DARK,
        )
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.command(
        name="ticket-stats", description="🎫 Ticket-Statistiken anzeigen"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_stats(self, interaction: discord.Interaction) -> None:
        s = db.ticket_stats(interaction.guild_id)
        cats = s["by_category"]
        lines = [
            f"{TICKET_CATEGORIES.get(k, {}).get('label', k)}: **{v}**"
            for k, v in sorted(cats.items(), key=lambda x: -x[1])
        ] or ["–"]
        e = base_embed(
            "🎫 Ticket-Statistiken",
            (
                f"**Gesamt:** {s['total']}\n"
                f"**Offen:** 🟢 {s['open']}\n"
                f"**Geschlossen:** 🔴 {s['closed']}\n\n"
                + "\n".join(lines)
            ),
            color=COLOR_MAIN,
        )
        await interaction.response.send_message(embed=e, ephemeral=True)

    # ------------------------------------------ Channel-Commands (im Ticket)
    async def _resolve(
        self, interaction: discord.Interaction, channel: discord.TextChannel | None
    ) -> tuple[discord.TextChannel, dict] | None:
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            await interaction.response.send_message(
                embed=error_embed("Kein gültiger Text-Channel."), ephemeral=True
            )
            return None
        ticket = db.get_ticket_by_channel(target.id)
        if not ticket:
            await interaction.response.send_message(
                embed=error_embed("Hier existiert kein Ticket."), ephemeral=True
            )
            return None
        return target, ticket

    def _ensure_staff(
        self, interaction: discord.Interaction, ticket: dict, *, owner_ok: bool = False
    ) -> bool:
        user = interaction.user
        assert isinstance(user, discord.Member)
        if is_staff(user, ticket["category"]):
            return True
        if owner_ok and user.id == int(ticket["owner_id"]):
            return True
        return False

    @app_commands.command(name="ticket-claim", description="🙋 Ticket beanspruchen")
    @app_commands.describe(channel="Ticket-Channel (Standard: aktueller)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_claim(
        self, interaction: discord.Interaction, channel: discord.TextChannel = None
    ) -> None:
        resolved = await self._resolve(interaction, channel)
        if not resolved:
            return
        ch, ticket = resolved
        user = interaction.user
        assert isinstance(user, discord.Member)
        if not self._ensure_staff(interaction, ticket):
            return await interaction.response.send_message(
                embed=error_embed("Keine Berechtigung."), ephemeral=True
            )
        if ticket["status"] != "open":
            return await interaction.response.send_message(
                embed=error_embed("Das Ticket ist geschlossen."), ephemeral=True
            )
        db.set_ticket_claimed(ch.id, user.id)
        await interaction.response.send_message(
            embed=success_embed("Beansprucht", f"{user.mention} übernimmt {ch.mention}.")
        )
        await self.log_action(
            interaction.guild,
            "Ticket beansprucht",
            f"**Kanal:** {ch.mention}\n**Durch:** {user.mention}",
            user,
            color=COLOR_DARK,
        )

    @app_commands.command(name="ticket-add", description="➕ Mitglied ins Ticket")
    @app_commands.describe(user="Mitglied", channel="Ticket-Channel (Standard: aktueller)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_add(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        channel: discord.TextChannel = None,
    ) -> None:
        resolved = await self._resolve(interaction, channel)
        if not resolved:
            return
        ch, ticket = resolved
        if not self._ensure_staff(interaction, ticket):
            return await interaction.response.send_message(
                embed=error_embed("Keine Berechtigung."), ephemeral=True
            )
        member = interaction.guild.get_member(user.id)
        if member is None:
            return await interaction.response.send_message(
                embed=error_embed("Dieses Mitglied ist nicht auf dem Server."),
                ephemeral=True,
            )
        try:
            await ch.set_permissions(
                member,
                view_channel=True,
                send_messages=True,
                attach_files=True,
                embed_links=True,
                read_message_history=True,
                reason=f"Hinzugefügt von {interaction.user}",
            )
        except discord.HTTPException:
            return await interaction.response.send_message(
                embed=error_embed("Berechtigung konnte nicht gesetzt werden."),
                ephemeral=True,
            )
        await interaction.response.send_message(
            embed=success_embed("Hinzugefügt", f"{member.mention} wurde hinzugefügt.")
        )

    @app_commands.command(name="ticket-remove", description="➖ Mitglied aus dem Ticket")
    @app_commands.describe(user="Mitglied", channel="Ticket-Channel (Standard: aktueller)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_remove(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        channel: discord.TextChannel = None,
    ) -> None:
        resolved = await self._resolve(interaction, channel)
        if not resolved:
            return
        ch, ticket = resolved
        if not self._ensure_staff(interaction, ticket):
            return await interaction.response.send_message(
                embed=error_embed("Keine Berechtigung."), ephemeral=True
            )
        if user.id == int(ticket["owner_id"]):
            return await interaction.response.send_message(
                embed=error_embed("Der Ticket-Ersteller kann nicht entfernt werden."),
                ephemeral=True,
            )
        member = interaction.guild.get_member(user.id)
        if member is None:
            return await interaction.response.send_message(
                embed=error_embed("Dieses Mitglied ist nicht auf dem Server."),
                ephemeral=True,
            )
        try:
            await ch.set_permissions(member, overwrite=None)
        except discord.HTTPException:
            return await interaction.response.send_message(
                embed=error_embed("Berechtigung konnte nicht entfernt werden."),
                ephemeral=True,
            )
        await interaction.response.send_message(
            embed=success_embed("Entfernt", f"{member.mention} wurde entfernt.")
        )

    @app_commands.command(name="ticket-close", description="🔒 Ticket schließen")
    @app_commands.describe(
        channel="Ticket-Channel (Standard: aktueller)",
        reason="Grund des Schließens",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_close(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel = None,
        reason: str = "Kein Grund angegeben",
    ) -> None:
        resolved = await self._resolve(interaction, channel)
        if not resolved:
            return
        ch, ticket = resolved
        if not self._ensure_staff(interaction, ticket, owner_ok=True):
            return await interaction.response.send_message(
                embed=error_embed("Keine Berechtigung."), ephemeral=True
            )
        if ticket["status"] != "open":
            return await interaction.response.send_message(
                embed=error_embed("Das Ticket ist bereits geschlossen."),
                ephemeral=True,
            )
        await self.perform_close(interaction, ticket, reason, channel=ch)

    @app_commands.command(name="ticket-reopen", description="🔓 Ticket wieder öffnen")
    @app_commands.describe(channel="Ticket-Channel (Standard: aktueller)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_reopen(
        self, interaction: discord.Interaction, channel: discord.TextChannel = None
    ) -> None:
        resolved = await self._resolve(interaction, channel)
        if not resolved:
            return
        ch, ticket = resolved
        if not self._ensure_staff(interaction, ticket, owner_ok=True):
            return await interaction.response.send_message(
                embed=error_embed("Keine Berechtigung."), ephemeral=True
            )
        if ticket["status"] == "open":
            return await interaction.response.send_message(
                embed=error_embed("Das Ticket ist bereits offen."), ephemeral=True
            )
        await self.perform_reopen(interaction, ch, ticket)

    @app_commands.command(name="ticket-transcript", description="📄 Transkript erstellen")
    @app_commands.describe(channel="Ticket-Channel (Standard: aktueller)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_transcript(
        self, interaction: discord.Interaction, channel: discord.TextChannel = None
    ) -> None:
        resolved = await self._resolve(interaction, channel)
        if not resolved:
            return
        ch, ticket = resolved
        if not self._ensure_staff(interaction, ticket, owner_ok=True):
            return await interaction.response.send_message(
                embed=error_embed("Keine Berechtigung."), ephemeral=True
            )
        await interaction.response.defer(ephemeral=True)
        path = await self.make_transcript(ch, ticket)
        if not path or not os.path.exists(path):
            return await interaction.followup.send(
                embed=error_embed("Transkript konnte nicht erstellt werden."),
                ephemeral=True,
            )
        await interaction.followup.send(
            embed=success_embed("Transkript", f"Ticket #{ticket['number']}"),
            file=discord.File(path),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tickets(bot))
