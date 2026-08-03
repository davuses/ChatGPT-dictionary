# My Dictionary

[中文说明](README.zh-CN.md)

A personal vocabulary web app for IELTS study, built with FastAPI and SQLite. Add words and phrases, write your own definitions in Markdown, attach usage examples, and review them later — with phonetic transcription, thesaurus lookups, and a built-in Markdown notes browser thrown in.

## Features

- **Entries & definitions** — add words/phrases, attach one or more Markdown-formatted definitions and an example sentence
- **IPA transcription** — automatic phonetic transcription of each word via [phonemizer](https://github.com/bootphon/phonemizer)
- **Thesaurus lookup** — pull synonyms and sense definitions from the Merriam-Webster Thesaurus API
- **Review bookmark** — mark your place in the entry list and jump back to it later
- **Visit tracking** — each entry tracks visit count and last-visited time
- **Multiple views** — browse all entries, entries-only, or entries with examples
- **Notes section** — browse and edit a folder of Markdown notes (e.g. IELTS study notes) with a generated table of contents
- **Markdown editing** — entries, definitions, examples, and notes are all edited with [EasyMDE](https://github.com/Ionaru/easy-markdown-editor)

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

3. Create the database tables:

   ```bash
   python database.py create-table
   ```

4. Run the app:

   ```bash
   uvicorn main:app --reload
   ```

   Then open `http://localhost:8000`.

## Notes

- Data is stored locally in `dictionary.db` (SQLite) and is not tracked in git.
