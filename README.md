# patchbot-bridge

A small bridge: it listens on a single Discord channel (the one PatchBot
posts update notifications to) and forwards every message to Slack via an
Incoming Webhook — including formatting (headers, bold text, clickable
links), not just raw text.

Runs as a single Python process (`discord.py` + `requests`), no database.
Idle memory usage is typically 50–80 MB, so it fits even on very small VPS
instances.

---

## Table of contents

1. [How it works](#1-how-it-works)
2. [Discord — creating the bot](#2-discord--creating-the-bot-step-by-step)
3. [Slack — Incoming Webhook](#3-slack--incoming-webhook-step-by-step)
4. [Option A: Debian 12 + LXC + systemd](#4-option-a-debian-12--lxc--systemd)
5. [Option B: Alpine Linux, small VPS (256 MB RAM / 1 GB disk)](#5-option-b-alpine-linux-small-vps-256-mb-ram--1-gb-disk)
6. [Testing](#6-testing)
7. [Management and updates](#7-management-and-updates)
8. [Troubleshooting](#8-troubleshooting)
9. [Limitations](#9-limitations)

---

## 1. How it works

- The bot connects to Discord over a WebSocket (gateway) and continuously
  listens for the `on_message` event.
- It filters messages down to a single, configured channel (ID in `.env`).
- If a message has an embed (this is how PatchBot sends notifications: game
  title, changelog, link, color, sometimes an image), the bridge converts it
  into a Slack `attachment` (colored side bar, linked title, body text,
  fields, footer).
- **It converts Discord's markdown syntax into Slack's syntax (mrkdwn)** —
  without this, something like `### Changes` would show up literally instead
  of as a bold header, and links like `[[134325]](url)` would appear as
  unclickable raw text. The bridge converts:
  - headers (`# / ## / ###`) → bold text,
  - bold `**text**` → `*text*` (Slack's syntax),
  - underline `__text__` → plain text (Slack has no underline),
  - links `[text](url)` → `<url|text>` (a clickable link in Slack).
- It POSTs the payload to the Slack Incoming Webhook, with 3 retries and
  backoff in case of a transient network error.

Configuration is via environment variables in the `.env` file:

| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Discord bot token |
| `DISCORD_CHANNEL_ID` | ID of the channel to forward messages from |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook URL |
| `BRIDGE_LOG_PATH` | (optional) path to the log file |

---

## 2. Discord — creating the bot (step by step)

### 2.1 Create the application

1. Go to **https://discord.com/developers/applications** and log in.
2. In the top-right corner, click the blue **New Application** button.
3. Enter a name, e.g. `PatchBot Bridge`, accept the terms, click **Create**.
4. You'll land on the **General Information** page — the left-hand menu
   (General Information, OAuth2, Bot, etc.) is what we'll use next.

### 2.2 Turn the application into a bot and get the token

1. Click **Bot** in the left menu.
2. The bot already exists (Discord creates it automatically with the
   application) — you'll see its name and icon.
3. In the **Token** section, click **Reset Token** (confirm with
   password/2FA if Discord asks) — the token is shown only once, so click
   **Copy** immediately.
4. Paste this token into `.env` as `DISCORD_TOKEN`. **Never share it or
   commit it to Git** — whoever has the token fully controls the bot.
5. Scroll down to **Privileged Gateway Intents** and enable **only**
   **MESSAGE CONTENT INTENT** (without it, the bot can't read message
   content/embeds). Leave the other two toggles off.
6. Click **Save Changes** at the bottom of the page.

### 2.3 Build the invite link

1. Click **OAuth2** in the left menu, then find the **URL Generator** section.
2. Under **Scopes**, check only `bot`.
3. Under **Bot Permissions**, check only: **View Channel**, **Read Message History**.
4. Copy the generated URL at the bottom of the page and open it in a new tab.
5. Pick your server from the **Add to Server** dropdown → **Continue** →
   **Authorize**.
6. The bot will appear in your server's member list (offline until you run
   the script).

### 2.4 Find the ID of the channel PatchBot posts to

1. In Discord: **User Settings** → **Advanced** → enable **Developer Mode**.
2. Right-click the channel PatchBot posts to → **Copy Channel ID**.
3. Paste the value into `.env` as `DISCORD_CHANNEL_ID`.

---

## 3. Slack — Incoming Webhook (step by step)

### 3.1 Create the Slack app

1. Go to **https://api.slack.com/apps**, log in with an account that has
   access to the `bartlabsdev` workspace.
2. Click **Create New App** → **From scratch**.
3. Name it e.g. `PatchBot Bridge`, workspace: **bartlabsdev**, click
   **Create App**.

### 3.2 Enable Incoming Webhooks

1. Click **Incoming Webhooks** in the left menu.
2. Toggle **Activate Incoming Webhooks** on.
3. Click **Add New Webhook to Workspace**.
4. Pick the target channel from the **Post to** dropdown (e.g. a dedicated
   `#patchbot-notifications`), click **Allow**.
5. You'll return to the page with a new row under **Webhook URLs for Your
   Workspace** — copy the URL (`https://hooks.slack.com/services/...`).
6. Paste it into `.env` as `SLACK_WEBHOOK_URL`.

### 3.3 Quick test before running the bridge

```bash
curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"Test from terminal - if you see this, the webhook works"}' \
  "PASTE_YOUR_WEBHOOK_URL_HERE"
```

Treat this URL like a password — anyone who has it can post to your channel.

---

## 4. Option A: Debian 12 + LXC + systemd

Use this option if you have a "normal" VPS running Debian (e.g. 1 GB RAM,
10 GB disk) with an LXC container.

### 4.1 LXC container (on the host)

```bash
lxc-create -n patchbridge -t debian -- -r bookworm
lxc-start -n patchbridge
lxc-attach -n patchbridge
```

### 4.2 System packages (inside the container)

```bash
apt update && apt install -y python3 python3-venv python3-pip
```

### 4.3 Install the application

```bash
mkdir -p /opt/patchbot-bridge
# copy bridge.py, requirements.txt, .env.example, patchbot-bridge.service there
cd /opt/patchbot-bridge

python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

cp .env.example .env
nano .env   # fill in DISCORD_TOKEN, DISCORD_CHANNEL_ID, SLACK_WEBHOOK_URL
```

### 4.4 System user

```bash
useradd --system --no-create-home --shell /usr/sbin/nologin patchbridge
mkdir -p /var/log/patchbot-bridge
chown -R patchbridge:patchbridge /opt/patchbot-bridge /var/log/patchbot-bridge
```

### 4.5 systemd service

```bash
cp patchbot-bridge.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now patchbot-bridge
systemctl status patchbot-bridge
journalctl -u patchbot-bridge -f
```

---

## 5. Option B: Alpine Linux, small VPS (256 MB RAM / 1 GB disk)

This is the option actually used in production for this project. Differences
from Debian: the package manager is `apk` (not `apt`), the C library is musl
(not glibc), and the init system is **OpenRC** (not systemd) — which is why
a separate `patchbot-bridge.openrc` file is needed instead of `.service`.

### 5.1 Swap (important at 256 MB RAM)

Installing Python packages with any C compilation can briefly exceed
256 MB RAM:

```sh
dd if=/dev/zero of=/swapfile bs=1M count=512
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo "/swapfile none swap sw 0 0" >> /etc/fstab
```

### 5.2 System packages via apk

```sh
apk update
apk add python3 py3-pip py3-virtualenv

# prebuilt binary packages, to avoid pip having to compile anything
# (saves both RAM and disk)
apk add py3-aiohttp py3-yarl py3-multidict py3-frozenlist py3-attrs
```

### 5.3 Install the application

```sh
mkdir -p /opt/patchbot-bridge
# copy bridge.py, requirements.txt, .env.example, patchbot-bridge.openrc there
cd /opt/patchbot-bridge

python3 -m venv --system-site-packages venv
./venv/bin/pip install --no-cache-dir -r requirements.txt
```

If pip still starts compiling something from source (you'll see
`Building wheel for ...` in the log), install build tools temporarily,
then remove them afterwards:

```sh
apk add --virtual .build-deps build-base musl-dev libffi-dev
./venv/bin/pip install --no-cache-dir -r requirements.txt
apk del .build-deps
```

```sh
cp .env.example .env
vi .env   # fill in DISCORD_TOKEN, DISCORD_CHANNEL_ID, SLACK_WEBHOOK_URL
```

### 5.4 System user and logs

```sh
addgroup -S patchbridge
adduser -S -G patchbridge -H -s /sbin/nologin patchbridge
mkdir -p /var/log/patchbot-bridge
chown -R patchbridge:patchbridge /opt/patchbot-bridge /var/log/patchbot-bridge
```

### 5.5 OpenRC service

The provided `patchbot-bridge.openrc` includes `respawn_max`,
`respawn_period`, and `respawn_delay` settings so OpenRC automatically
restarts the process if it crashes (e.g. after an unhandled disconnect),
without needing manual intervention.

```sh
cp patchbot-bridge.openrc /etc/init.d/patchbot-bridge
chmod +x /etc/init.d/patchbot-bridge
rc-update add patchbot-bridge default
rc-service patchbot-bridge start
rc-service patchbot-bridge status
tail -f /var/log/patchbot-bridge/bridge.log
```

### 5.6 Cleaning up disk space

```sh
rm -rf /var/cache/apk/*
```

### 5.7 Realistic resource assessment

- Idle bot: 50–80 MB RAM, minimal network traffic.
- The riskiest moment is dependency installation itself — hence the swap
  and `--system-site-packages` above.
- If disk space runs out during install: `df -h` and
  `du -sh /opt/patchbot-bridge/venv` to see what's taking up space.
- 1 GB of disk leaves no margin for the future (logs, apk upgrades), but is
  enough for the bridge itself.

---

## 6. Testing

After starting the service (either option), the log should show:

```
Logged in as PatchBot Bridge#1234 (ID: ...)
Listening on channel #patchbot-notifications (123456789012345678)
```

Post any message in the watched Discord channel — it should show up on
Slack (formatted: bold text, clickable links instead of raw markdown).

---

## 7. Management and updates

**Alpine / OpenRC:**

```sh
rc-service patchbot-bridge restart   # after changing .env or the code
rc-service patchbot-bridge stop
tail -f /var/log/patchbot-bridge/bridge.log
```

**Debian / systemd:**

```bash
systemctl restart patchbot-bridge
systemctl stop patchbot-bridge
journalctl -u patchbot-bridge -n 100 --no-pager
```

Swapping out just the code (`bridge.py`) without changing
`requirements.txt` doesn't require reinstalling any packages — just
replace the file and restart the service.

---

## 8. Troubleshooting

### Messages arrive duplicated

The most common cause: **two `bridge.py` processes running at the same
time** (e.g. an old one on a previous server, plus a new one). Check:

```sh
ps aux | grep bridge.py
```

If you see more than one process (besides the `grep` itself), stop the
extra one:

```sh
pkill -f bridge.py
rc-service patchbot-bridge start    # or: systemctl start patchbot-bridge
```

A second possible cause: a single process, but the request to Slack
exceeded the 10-second timeout and the script retried, even though the
first message actually went through. Check the log:

```sh
grep -E "network error|responded" /var/log/patchbot-bridge/bridge.log
```

The most reliable way to rule out a "forgotten" old bridge instance (e.g.
on a previously used server) is to **rotate the bot token**: Discord
Developer Portal → your application → **Bot** → **Reset Token**, then paste
the new token only into the currently used `.env`. The old token stops
working immediately, so any forgotten process will stop being able to
connect.

### Raw markdown instead of formatted text on Slack (`### Changes`, `[text](url)`)

Make sure you're running the current version of `bridge.py`, which
includes the `discord_markdown_to_slack()` conversion function — older
versions forwarded the embed description without converting it. Replace
the file and restart the service.

### Bot doesn't see the channel / `on_ready` shows a warning

Check that the bot has the **View Channel** permission on that specific
channel (it may have server access but not channel access, if the channel
has permission overrides).

### 403/404 error when posting to Slack

Usually means an outdated or incorrectly copied `SLACK_WEBHOOK_URL` —
generate a new webhook following the steps in section 3.

### Messages stopped arriving entirely, no crash logged after a certain point

Check whether the process is actually still running:

```sh
ps aux | grep bridge.py
```

If nothing shows up (besides `grep` itself), the process died and wasn't
restarted. Common causes on a 256 MB RAM VPS: the OOM killer terminated it.
Check:

```sh
dmesg | grep -i -E "kill|oom" | tail -20
```

If you see `bridge.py` or `python3` mentioned there, RAM pressure was the
cause. Make sure `patchbot-bridge.openrc` has `respawn_max` / `respawn_period`
/ `respawn_delay` set (see section 5.5) so OpenRC restarts the process
automatically next time, instead of leaving it dead.

### Service stuck in `unsupervised` / "already starting"

```
rc-service patchbot-bridge start
 * WARNING: patchbot-bridge is already starting
rc-service patchbot-bridge status
 * status: unsupervised
```

This means the service's internal state got stuck — usually after the
process died in an unusual way and OpenRC didn't clean up its own
bookkeeping. Fix:

```sh
rc-service patchbot-bridge zap
rm -f /run/patchbot-bridge.pid
rc-service patchbot-bridge start
rc-service patchbot-bridge status
```

`status` should now say `started` rather than `unsupervised`.

One-liner for the same fix, safe to paste as a single line if you're doing
this from a phone SSH client:

```sh
rc-service patchbot-bridge zap; rm -f /run/patchbot-bridge.pid; rc-service patchbot-bridge start; rc-service patchbot-bridge status
```

### `/etc/init.d/patchbot-bridge` is read-only when trying to edit it

Check these three things, in order:

```sh
whoami
```

If this isn't `root`, you likely don't have write access to files in
`/etc/init.d/` — use `sudo vi ...` or `su -` first.

```sh
ls -l /etc/init.d/patchbot-bridge
```

If the permission bits show no `w` at all (e.g. `-r--r--r--`), fix them:

```sh
chmod 755 /etc/init.d/patchbot-bridge
```

```sh
mount | grep " / "
```

If this shows `ro` instead of `rw`, the whole filesystem is mounted
read-only (can happen after an unclean restart/OOM on small VPS instances)
— remount it:

```sh
mount -o remount,rw /
```

---

## 9. Limitations

- This is a "live" bridge — if the server loses connectivity for a while,
  messages PatchBot sent during that time are not replayed afterwards (no
  channel history backfill on restart).
- Very long changelogs get truncated by Slack's UI itself ("Show more") —
  this is a Slack limitation and can't be fully disabled.
- `discord.py` requires Python 3.9+; both Debian 12 and current Alpine ship
  with a new enough Python by default.
