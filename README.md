# Work Time Tracker

A self-hosted app that automatically tracks work hours by reading OS login/logout history. Answers the one question that matters: **can I stop working yet?**

The dashboard shows a live stop time based on how many hours you've worked this week, adjusted for any surplus or deficit carried from prior weeks. No timers to start or stop — just log in to your computer and it tracks itself.

→ [Full project overview](docs/overview.md)

---

## Features

- Automatic login/logout tracking on Ubuntu (Windows agent planned)
- Screen lock/unlock counted as work pauses
- Running hours bank — overworked weeks reduce future targets, underworked weeks raise them
- Per-computer session log with is-work toggles
- Manual entry for holidays, office days, and other exceptions
- Daily and weekly charts
- Dark-themed web UI, fully responsive

---

## Requirements

- Docker and Docker Compose (for the server)
- Python 3.8+ (for the Ubuntu sync agent)
- Ubuntu with GNOME desktop (for the lock/unlock listener)

---

## Server Setup

The server runs in Docker and exposes the web UI and API on port 8000.

```bash
git clone <repo>
cd worktime-tracker
docker compose up -d
```

Open `http://localhost:8000` (or `http://<your-server-ip>:8000` from another machine on the network).

SQLite data is stored in `./data/worktime.db` on the host — back it up with a simple cron job. Edit `docker-compose.yml` to change the data directory path if needed.

---

## Ubuntu Agent

The Ubuntu agent runs as two systemd user services:

- **`worktime-sync`** — reads the last 30 days of login/logout history from the systemd journal every 5 minutes and syncs it to the server
- **`worktime-lock-listener`** — listens for screen lock/unlock events in real time via D-Bus and posts them immediately

**Install:**

```bash
bash agents/ubuntu/install.sh
```

The script prompts for your server URL and a name for this computer, installs any missing dependencies (`python3-dbus`, `python3-gi`), writes the systemd unit files, and starts both services. Running it again is safe — it updates config and restarts services without any manual cleanup.

**Check logs:**

```bash
journalctl --user -u worktime-sync -f
journalctl --user -u worktime-lock-listener -f
```

---

## Project Layout

```
server/          FastAPI server + SQLite + web UI
agents/
  ubuntu/        Ubuntu sync agent and lock listener
data/            SQLite database (created on first run)
tests/           Test suite
```
