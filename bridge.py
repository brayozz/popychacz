#!/usr/bin/env python3
"""
patchbot-bridge
================
Nasłuchuje na jednym, konkretnym kanale Discorda (tym, na który PatchBot
wysyła powiadomienia) i każdą nową wiadomość przekazuje na Slacka
za pomocą Incoming Webhook.

Wymagane zmienne środowiskowe (patrz .env.example):
    DISCORD_TOKEN        - token bota Discord
    DISCORD_CHANNEL_ID    - ID kanału, z którego mają być przekazywane wiadomości
    SLACK_WEBHOOK_URL     - URL Incoming Webhooka Slacka

Autor: mini-bridge napisany na potrzeby VPS (Debian 12, LXC, 1GB RAM).
"""

import os
import re
import sys
import logging
import time
from logging.handlers import RotatingFileHandler

import requests
import discord
from dotenv import load_dotenv

# --------------------------------------------------------------------------
# Konfiguracja
# --------------------------------------------------------------------------

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

LOG_PATH = os.getenv("BRIDGE_LOG_PATH", "/var/log/patchbot-bridge/bridge.log")

# ile razy próbujemy wysłać do Slacka zanim się poddamy dla danej wiadomości
SLACK_MAX_RETRIES = 3
SLACK_RETRY_BACKOFF_SECONDS = 2

# --------------------------------------------------------------------------
# Logowanie (plik z rotacją, żeby nie zapchać 10GB dysku)
# --------------------------------------------------------------------------

logger = logging.getLogger("patchbot-bridge")
logger.setLevel(logging.INFO)

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

# log na stdout (systemd/journalctl to i tak przechwyci)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# opcjonalny plik logu z rotacją (max 2MB x 3 pliki = max 6MB)
try:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
except OSError:
    # brak uprawnień do katalogu logów - działamy dalej tylko na stdout
    logger.warning(
        "Nie udało się utworzyć pliku logu w %s - loguję tylko na stdout", LOG_PATH
    )


def validate_config():
    missing = []
    if not DISCORD_TOKEN:
        missing.append("DISCORD_TOKEN")
    if not DISCORD_CHANNEL_ID:
        missing.append("DISCORD_CHANNEL_ID")
    if not SLACK_WEBHOOK_URL:
        missing.append("SLACK_WEBHOOK_URL")
    if missing:
        logger.error("Brakuje zmiennych środowiskowych: %s", ", ".join(missing))
        sys.exit(1)
    try:
        int(DISCORD_CHANNEL_ID)
    except ValueError:
        logger.error("DISCORD_CHANNEL_ID musi być liczbą (ID kanału Discord)")
        sys.exit(1)


validate_config()
TARGET_CHANNEL_ID = int(DISCORD_CHANNEL_ID)

# --------------------------------------------------------------------------
# Konwersja wiadomości Discord -> payload Slacka
# --------------------------------------------------------------------------


def discord_color_to_hex(color: discord.Colour | None) -> str:
    if color is None:
        return "#5865F2"  # domyślny fiolet Discorda
    return f"#{color.value:06x}"


# Discord i Slack mają inną, niekompatybilną odmianę "markdown" (Slack nazywa
# to "mrkdwn"). Bez konwersji użytkownik widzi surowe znaczniki (### itd.)
# oraz niedziałające linki w formacie [tekst](url).

# [tekst](https://url) -> <https://url|tekst>
# non-greedy, żeby poprawnie obsłużyć też zagnieżdżone nawiasy typu
# [[134325]](https://...) - takiego formatu linków używa PatchBot
_MD_LINK_RE = re.compile(r"\[(.+?)\]\((https?://[^\s)]+)\)")

# nagłówki markdown (#, ##, ### ...) na początku linii -> pogrubiona linia
# (Slack mrkdwn nie ma nagłówków, tylko pogrubienie pojedynczą gwiazdką)
_MD_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$", re.MULTILINE)

# **pogrubienie** (Discord) -> *pogrubienie* (Slack)
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")

# __podkreślenie__ (Discord, brak odpowiednika w Slacku) -> zwykły tekst
_MD_UNDERLINE_RE = re.compile(r"__(.+?)__")


def discord_markdown_to_slack(text: str) -> str:
    """Konwertuje najczęstsze znaczniki markdown Discorda na składnię
    zrozumiałą dla Slacka (mrkdwn), żeby wiadomość nie wyglądała na "surową"."""
    if not text:
        return text

    text = _MD_HEADER_RE.sub(r"*\1*", text)
    text = _MD_BOLD_RE.sub(r"*\1*", text)
    text = _MD_UNDERLINE_RE.sub(r"\1", text)
    text = _MD_LINK_RE.sub(r"<\2|\1>", text)
    return text


def build_slack_payload(message: discord.Message) -> dict:
    """Buduje payload dla Slack Incoming Webhook na podstawie wiadomości Discorda.

    PatchBot wysyła powiadomienia zwykle jako embed (tytuł gry/aplikacji,
    opis zmian, link, kolor). Obsługujemy to, a także zwykły tekst jako fallback.
    """
    attachments = []

    if message.embeds:
        for embed in message.embeds:
            attachment = {
                "color": discord_color_to_hex(embed.colour),
            }

            if embed.author and embed.author.name:
                attachment["author_name"] = embed.author.name
                if embed.author.url:
                    attachment["author_link"] = embed.author.url
                if embed.author.icon_url:
                    attachment["author_icon"] = embed.author.icon_url

            if embed.title:
                # tytuł nie powinien zawierać markdown, ale na wszelki wypadek
                attachment["title"] = discord_markdown_to_slack(embed.title)
            if embed.url:
                attachment["title_link"] = embed.url
            if embed.description:
                attachment["text"] = discord_markdown_to_slack(embed.description)

            if embed.fields:
                attachment["fields"] = [
                    {
                        "title": discord_markdown_to_slack(field.name),
                        "value": discord_markdown_to_slack(field.value),
                        "short": field.inline,
                    }
                    for field in embed.fields
                ]

            if embed.thumbnail and embed.thumbnail.url:
                attachment["thumb_url"] = embed.thumbnail.url
            if embed.image and embed.image.url:
                attachment["image_url"] = embed.image.url

            if embed.footer and embed.footer.text:
                attachment["footer"] = discord_markdown_to_slack(embed.footer.text)

            attachment["ts"] = int(message.created_at.timestamp())
            attachments.append(attachment)

    payload = {}

    # zwykły tekst wiadomości (jeśli PatchBot coś dopisał poza embedem)
    if message.content:
        payload["text"] = discord_markdown_to_slack(message.content)

    if attachments:
        payload["attachments"] = attachments
    elif not message.content:
        # ani treści, ani embedów - nic sensownego do przekazania
        return {}

    return payload


def send_to_slack(payload: dict) -> bool:
    if not payload:
        logger.info("Pusty payload - pomijam wysyłkę do Slacka")
        return True

    for attempt in range(1, SLACK_MAX_RETRIES + 1):
        try:
            response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
            if response.status_code == 200:
                return True
            logger.warning(
                "Slack odpowiedział %s: %s (próba %d/%d)",
                response.status_code,
                response.text,
                attempt,
                SLACK_MAX_RETRIES,
            )
        except requests.RequestException as exc:
            logger.warning(
                "Błąd sieci przy wysyłce do Slacka (próba %d/%d): %s",
                attempt,
                SLACK_MAX_RETRIES,
                exc,
            )

        if attempt < SLACK_MAX_RETRIES:
            time.sleep(SLACK_RETRY_BACKOFF_SECONDS * attempt)

    logger.error("Nie udało się dostarczyć wiadomości do Slacka po %d próbach", SLACK_MAX_RETRIES)
    return False


# --------------------------------------------------------------------------
# Klient Discord
# --------------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True  # wymagane, by odczytać treść/embedy wiadomości

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    logger.info("Zalogowano jako %s (ID: %s)", client.user, client.user.id)
    channel = client.get_channel(TARGET_CHANNEL_ID)
    if channel is None:
        logger.warning(
            "Nie widzę kanału o ID %s - sprawdź, czy bot jest zaproszony na serwer "
            "i ma uprawnienia 'View Channel' na tym kanale",
            TARGET_CHANNEL_ID,
        )
    else:
        logger.info("Nasłuchuję na kanale #%s (%s)", channel.name, channel.id)


@client.event
async def on_message(message: discord.Message):
    if message.channel.id != TARGET_CHANNEL_ID:
        return

    # nie przekazujemy własnych wiadomości bota (na wszelki wypadek, gdyby kiedyś coś pisał)
    if message.author.id == client.user.id:
        return

    logger.info(
        "Nowa wiadomość od %s na #%s (embeds=%d)",
        message.author,
        message.channel.name,
        len(message.embeds),
    )

    payload = build_slack_payload(message)
    ok = send_to_slack(payload)
    if ok:
        logger.info("Przekazano do Slacka OK")


@client.event
async def on_disconnect():
    logger.warning("Rozłączono z Discordem (biblioteka spróbuje wznowić połączenie)")


def main():
    logger.info("Startuję patchbot-bridge...")
    client.run(DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
