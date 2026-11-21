"""Helfer für einheitliche Babyblaue Embeds."""

from __future__ import annotations

import discord

from config import (
    AUTHOR_NAME,
    COLOR_ERROR,
    COLOR_MAIN,
    COLOR_SUCCESS,
    COLOR_WARNING,
    EMBED_IMAGE_URL,
    FOOTER_TEXT,
)


def base_embed(
    title: str | None = None,
    description: str | None = None,
    *,
    color: int | None = None,
    footer: bool = True,
) -> discord.Embed:
    """Einheitliches PrimeFFA-Embed."""
    e = discord.Embed(title=title, description=description, color=color or COLOR_MAIN)
    if footer and FOOTER_TEXT:
        e.set_footer(text=FOOTER_TEXT)
    if EMBED_IMAGE_URL:
        e.set_image(url=EMBED_IMAGE_URL)
    return e


def error_embed(description: str) -> discord.Embed:
    e = discord.Embed(title="❌ Fehler", description=description, color=COLOR_ERROR)
    if FOOTER_TEXT:
        e.set_footer(text=FOOTER_TEXT)
    return e


def success_embed(title: str, description: str) -> discord.Embed:
    e = discord.Embed(title=f"✅ {title}", description=description, color=COLOR_SUCCESS)
    if FOOTER_TEXT:
        e.set_footer(text=FOOTER_TEXT)
    return e


def warn_embed(title: str, description: str) -> discord.Embed:
    e = discord.Embed(title=f"⚠️ {title}", description=description, color=COLOR_WARNING)
    if FOOTER_TEXT:
        e.set_footer(text=FOOTER_TEXT)
    return e


def info_embed(title: str, description: str) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=COLOR_MAIN)
    if FOOTER_TEXT:
        e.set_footer(text=FOOTER_TEXT)
    return e


def set_author(embed: discord.Embed) -> discord.Embed:
    embed.set_author(name=AUTHOR_NAME)
    return embed


def ts(epoch: float, style: str = "f") -> str:
    return f"<t:{int(epoch)}:{style}>"


def dur(seconds: int) -> str:
    s = int(seconds)
    d, rem = divmod(s, 86400)
    h, rem = divmod(rem, 3600)
    m, sec = divmod(rem, 60)
    parts = []
    if d:
        parts.append(f"{d}T")
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if sec or not parts:
        parts.append(f"{sec}s")
    return "".join(parts)
