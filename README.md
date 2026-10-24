# Telegram File Store Link Recovery Bot

A Python Telegram bot + Telegram Mini App to replace only the username in inline-button links such as:

`https://t.me/OldFileStoreBot?start=AbC123xYz`

with:

`https://t.me/NewFileStoreBot?start=AbC123xYz`

It scans existing channel history, monitors new posts, previews matches before applying, and persists jobs in MongoDB so a worker restart can resume them.

## Important limitations

- The MTProto user account must be authorized, have access to the channel, and be permitted by Telegram to edit the relevant message's reply markup.
- Bot API access alone cannot reliably scan a channel's entire historical archive. This project uses Telethon (MTProto) for history and message edits.
- The replacement bot must understand the preserved `start` token and have access to the corresponding file/data. This tool only changes links; it does not migrate files, tokens, or databases.
- Telegram can impose flood waits and other restrictions. The worker respects Telethon FloodWait delays and throttles edits.
- Only URL buttons whose hostname is `t.me` or `telegram.me` and whose path username matches the configured old username are eligible. Message text, media, captions, button labels, button order, and unrelated buttons are not rewritten.
- Telegram's API may reject edits for messages that are too old, inaccessible, or otherwise not editable. Those are recorded as failures; the app does not bypass platform restrictions.

## Architecture

- FastAPI serves the Mini App and JSON API.
- aiogram provides `/start` and the dashboard launch button.
- Telethon (MTProto user session) scans history, watches new posts, and edits reply markup only.
- MongoDB stores channel settings, indexed posts, jobs, and per-button audit results.
- Run `ROLE=web` and `ROLE=worker` as separate services in production. Both use the same MongoDB database.

## Local setup

1. Create a Telegram bot with BotFather and set `BOT_TOKEN` / `BOT_USERNAME`.
2. Obtain `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` from https://my.telegram.org.
3. Create a MongoDB database, then copy `.env.example` to `.env` and fill in values.
4. Install Python 3.12+ and dependencies:

   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

5. Generate the Telethon session string interactively:

   ```bash
   python -m app.make_session
   ```

   Copy the printed session string into `TELEGRAM_SESSION_STRING`. Treat it like a password; never commit or share it.

6. Run the web app:

   ```bash
   ROLE=web uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

7. In another terminal run the bot and worker:

   ```bash
   ROLE=worker python -m app.worker
   ```

   For development only, `ROLE=all uvicorn app.main:app --host 0.0.0.0 --port 8000` runs web + bot + worker in one process.

## Telegram setup

- Add the bot to your channel as an administrator if you want it to receive Bot API channel updates. The Telethon user account also needs access to the channel for history scans and edits.
- Set the Mini App URL in BotFather (Menu Button / Main Mini App) to your deployed HTTPS URL.
- Add the same URL as `WEBAPP_URL`.
- Add numeric Telegram user IDs to `ADMIN_USER_IDS`. Only these users can access the dashboard.
- Add channels through the dashboard by entering a public username (`@channel`) or numeric channel ID (`-100...`). The Telethon account must already have access.

## Workflow

1. Open the bot and tap **Open Recovery Dashboard**.
2. Add a channel and set the old/new File Store bot usernames (without `@`).
3. Start a history scan. It is resumable and indexes button URLs.
4. Preview replacement. The preview is read-only and reports the number of eligible buttons/posts.
5. Confirm the job. The worker fetches each latest message, re-checks the target URL, edits only reply markup, and logs outcomes.
6. New posts in monitored channels are indexed automatically. New posts with the old username can be repaired by creating a new replacement job for the channel.

## Deploy on Koyeb / Render

Deploy two services from this repository:

### Web service
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Environment: set all common variables, `ROLE=web`.

### Worker service
- Build: `pip install -r requirements.txt`
- Start: `python -m app.worker`
- Environment: same secrets/database, `ROLE=worker`.
- Do not run multiple workers with the same Telethon session string at the same time. One worker should own the session.

Set `WEBAPP_URL` to the public HTTPS web service URL. Configure that URL in BotFather. If the host requires a health check, use `/health`.

## Security and operational notes

- Telegram Web App `initData` is validated server-side using the bot token.
- The API also checks the Telegram user ID against `ADMIN_USER_IDS`.
- Use HTTPS in production.
- Do not expose `.env`, session strings, bot tokens, API hashes, or MongoDB credentials.
- MongoDB is the durable job queue; jobs are not stored only in process memory.
- Do not use the dashboard from a browser outside Telegram: requests without valid Telegram Mini App init data are rejected.
- Review the audit log before any broad recovery. Start with a small test channel and a few messages.
