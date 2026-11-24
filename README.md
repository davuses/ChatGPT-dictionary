# Glossbook

[中文说明](README.zh-CN.md)

A private, personal English vocabulary builder and active-recall web app, built with FastAPI and SQLite. Add words and phrases, curate your own definitions in Markdown, attach real-world usage examples, and reinforce them with fill-in-the-blank quizzes, phonetic transcription, cross-linked thesaurus lookups, and a built-in Markdown study notes browser.

![Entry list](docs/screenshot-list.png)
![Word detail](docs/screenshot-entry.png)

## Features

- **Entries & definitions** — add words/phrases, write your own Markdown-formatted definitions, and attach real-world context and usage examples
- **Fill-in-the-blank quiz & review sessions** — low-pressure active-recall cards on the dashboard plus a keyboard-driven `/review` session mode, pulling sentences from your own saved contexts and examples
- **Live search** — instant search across words, contexts, and examples with match highlighting
- **IPA transcription & audio** — automatic phonetic transcription via [phonemizer](https://github.com/bootphon/phonemizer) with pronunciation playback
- **Thesaurus lookup** — pull synonyms and sense definitions from the Merriam-Webster Thesaurus API, cross-linked to words already in your dictionary
- **Review bookmark** — mark your place in the entry list and jump back to it later
- **Visit tracking** — each entry tracks visit count and last-visited time
- **Multiple views** — browse all entries, entries-only, entries with examples, or the **Needs Definition** backlog for newly captured words
- **Study notes** — browse and edit a folder of personal English study Markdown notes with a generated table of contents (admin-only)
- **Invite-only multi-user** — generate one-time invite links and password reset links from `/admin`; each user gets a completely isolated dictionary, quiz, `/inbox`, and per-device Chrome extension API tokens under `/account`
- **Markdown editing** — definitions, examples, and study notes are edited with [EasyMDE](https://github.com/Ionaru/easy-markdown-editor) (sanitized with `nh3` on render), while entries use quick plain-text word and context fields

## Tech stack

- [FastAPI](https://fastapi.tiangolo.com/) + [Jinja2](https://jinja.palletsprojects.com/) templates
- [SQLAlchemy](https://www.sqlalchemy.org/) ORM over SQLite
- [markdown2](https://github.com/trentm/python-markdown2) for rendering Markdown content
- [phonemizer](https://github.com/bootphon/phonemizer) for IPA transcription
- Vanilla JS + [EasyMDE](https://github.com/Ionaru/easy-markdown-editor) on the frontend

## Setup

Requires Python 3.12+.

1. Install dependencies (via [uv](https://github.com/astral-sh/uv) or pip):

   ```bash
   uv sync
   # or
   pip install -r requirements.txt
   ```

   IPA transcription also requires the `espeak-ng` backend:

   ```bash
   sudo apt-get install espeak-ng
   ```

2. Copy the example config and fill in your values:

   ```bash
   cp config.toml.example config.toml
   ```

   - `notes_folder` — a local directory of Markdown notes to browse under `/notes/`
   - `mw_thesaurus_api_key` — a free API key from the [Merriam-Webster Developer Center](https://dictionaryapi.com/) (used for the synonyms feature)

3. Configure your personal login account. Generate an Argon2 password hash and
   a random session secret:

   ```bash
   uv run python -c "from pwdlib import PasswordHash; print(PasswordHash.recommended().hash(input('Password: ')))"
   uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Add the resulting values to the `[auth]` section of `config.toml`:

   ```toml
   [auth]
   admin_username = "admin"
   admin_password_hash = "$argon2id$..."
   session_secret = "the-random-session-secret"
   https_only = true
   ```

   Production uses secure HTTPS-only session cookies (valid for 30 days). For
   an HTTP-only local-network test, temporarily set `https_only = false`; never
   use that value on a public-facing deployment. The `DICTIONARY_*` environment
   variables remain optional overrides for deployments that prefer them.

4. Create the database tables:

   ```bash
   python database.py create-table
   ```

5. Run the app:

   ```bash
   uvicorn main:app --reload
   ```

   Then open `http://localhost:8000`.

   To test from another device on the same trusted local network:

   ```bash
   export DICTIONARY_HTTPS_ONLY=false
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

   Open `http://<computer-lan-ip>:8000`. Restore
   `DICTIONARY_HTTPS_ONLY=true` (or remove the override) for production.

## Access control & multi-user

- The entire app is private and invite-only: all dictionary pages, quizzes,
  synonyms, bookmarks, `/inbox`, `/account`, and mutation endpoints require
  signing in at `/login`.
- Only `/login`, `/register` (with a valid one-time invite link),
  `/reset-password` (with an admin-issued one-time reset link), and `/static/*`
  assets are accessible before authentication.
- Each user's entries, definitions, quizzes, bookmarks, and `/inbox` are
  strictly isolated. Filesystem study notes (`/notes/*`) and `/admin` are
  admin-only (`403` for non-admin accounts).
- Signed sessions use `HttpOnly`, `SameSite=Lax` cookies (and `Secure` when
  `https_only = true`) with a 30-day lifetime and instant invalidation via
  `session_version` on password changes, resets, or account disable.
- Every browser state-changing request requires a CSRF token, and user-authored
  Markdown is sanitized with `nh3` before rendering.
- The `/api/v1/*` capture endpoints accept either an authenticated browser
  session (with `X-CSRF-Token` on mutations) or a per-user `Bearer` token
  created in `/account` (stored SHA-256 hashed, revocable per device,
  fail-closed when invalid or disabled).
- FastAPI's `/docs`, `/redoc`, and `/openapi.json` endpoints are disabled.
- If deployed behind a reverse proxy (Caddy/nginx/Cloudflare Tunnel), pass
  `--proxy-headers --forwarded-allow-ips=...` to Uvicorn so auth rate limiting
  sees real client IPs.
- Emergency admin password reset from the server CLI:

  ```bash
  python database.py reset-password --username admin
  ```

## Notes

- Data is stored locally in `dictionary.db` (SQLite) and is not tracked in git.
- On startup against a legacy single-user `dictionary.db`, the app automatically
  creates a WAL-safe backup (`dictionary.db.bak-*`) and migrates existing data
  to the bootstrap admin account.

## Chrome Side Panel extension (optional)

An unpacked Manifest V3 Chrome extension lives in [`extension/`](extension/) for taking per-page Markdown scratchpad notes and batch-capturing words/phrases (with YouTube playback timestamps + full-sentence captions or article sentence selection) directly into your dictionary:

1. Sign in to the web app, open **Account** (`/account`), and generate a per-device API token (each user can create separate tokens for laptop/desktop and revoke them individually).
2. Open `chrome://extensions`, enable **Developer mode**, click **Load unpacked**, and select the `extension/` folder.
3. Click the extension icon to open the Side Panel, click **Settings**, enter your server URL (e.g. `http://localhost:8000`) and your API token, and click **Save & test**.
4. You can also review, edit, and batch-promote captured items from any device at `/inbox`.
