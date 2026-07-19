# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`patchbot-bridge` is a single-file Python bridge that listens on one Discord channel (where PatchBot posts game/app update notifications) and forwards every message to Slack via an Incoming Webhook, preserving formatting (headers, bold, links) by converting Discord markdown to Slack's mrkdwn syntax.

The entire application is `bridge.py` — there is no package structure, no test suite, and no build step. It runs as a single long-lived Python process (`discord.py` gateway client + `requests` for outbound HTTP), designed to fit on very small VPS instances (as little as 256 MB RAM).

## Running locally

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env   # then fill in DISCORD_TOKEN, DISCORD_CHANNEL_ID, SLACK_WEBHOOK_URL
./venv/bin/python3 bridge.py
```

Config is loaded via `python-dotenv` from `.env` (see `.env.example` for all variables). `bridge.py` validates required env vars at import time and exits with an error if any are missing or if `DISCORD_CHANNEL_ID` isn't numeric.

There are no automated tests, linter, or formatter configured in this repo. Verify changes by running the bridge against a real (or test) Discord channel/Slack webhook and checking the log output, per the "Testing" section of README.md.

## Architecture

Everything lives in `bridge.py`, structured top to bottom as:

1. **Config loading & validation** — env vars read via `os.getenv`, validated by `validate_config()`, process exits (`sys.exit(1)`) on missing/invalid config.
2. **Logging** — a `RotatingFileHandler` (2MB × 3 backups) plus stdout, so logs are bounded on disk-constrained VPS instances. Falls back to stdout-only if the log directory isn't writable.
3. **Discord → Slack markdown conversion** (`discord_markdown_to_slack` and the `_MD_*_RE` regexes) — Discord and Slack use incompatible markdown dialects. This function converts headers (`#`/`##`/`###`) to bold, `**bold**` to `*bold*`, strips `__underline__` (no Slack equivalent), and rewrites `[text](url)` links to Slack's `<url|text>` form. Link regex is non-greedy specifically to handle PatchBot's `[[134325]](url)`-style nested-bracket links.
4. **Payload building** (`build_slack_payload`) — converts a `discord.Message` into a Slack webhook payload. PatchBot notifications typically arrive as Discord embeds (title, description, color, fields, footer, thumbnail/image), which get mapped to a single Slack `attachment` per embed. Plain message content (if any) is also forwarded as top-level `text`. Returns `{}` if there's nothing worth sending.
5. **Slack delivery** (`send_to_slack`) — POSTs the payload with up to `SLACK_MAX_RETRIES` (3) attempts and linear backoff (`SLACK_RETRY_BACKOFF_SECONDS * attempt`) on non-200 responses or network errors.
6. **Discord client & event handlers** — a single `discord.Client` with `message_content` intent enabled (required to read embed/message content). `on_message` filters to `TARGET_CHANNEL_ID`, ignores the bot's own messages, then builds and sends the Slack payload. `on_ready` logs whether the configured channel is actually visible to the bot (helps diagnose missing "View Channel" permission).

Everything is synchronous/blocking inside `send_to_slack` (using `requests`, not an async HTTP client) even though it's called from an `async` Discord event handler — this is a deliberate simplicity trade-off given the low message volume PatchBot generates, not an oversight.

## Deployment

Two deployment targets are documented in detail in README.md:

- **Debian 12 + LXC + systemd** — uses `patchbot-bridge.service` (not present in this repo; created during deployment per README section 4.5).
- **Alpine Linux (production target)** — uses `patchbot-bridge.openrc`, the actual init script committed here. Alpine uses `apk`, musl libc, and OpenRC instead of systemd, which is why this file exists separately from a systemd unit. Notable OpenRC config: `respawn_max=10` / `respawn_period=300` / `respawn_delay=5` for auto-restart after crashes, and a `start_pre()` that ensures the log directory exists with correct ownership before start.

When changing `bridge.py` only (no dependency changes), redeploying is just replacing the file and restarting the service (`rc-service patchbot-bridge restart` or `systemctl restart patchbot-bridge`) — no reinstall needed.

Never commit `.env`, real Discord tokens, or Slack webhook URLs — `.env.example` is the template; actual secrets stay only on the deployed host.
