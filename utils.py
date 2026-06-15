import os
import re
import time
import tomllib
import urllib
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import markdown2
from bs4 import BeautifulSoup
from fastapi import HTTPException
from phonemizer import phonemize

from database import Entry, db_get_all_entries
from wordhoard import Synonyms


def get_IPA(word) -> str:
    a = phonemize(word, strip=True, with_stress=True)
    if isinstance(a, str):
        a = a.replace("ɹ", "r").replace("ɐ", "ə")
        return a
    else:
        return str(a)


cached_all_words: dict[str, list[int]] = {}


def invalidate_words_cache() -> None:
    cached_all_words.clear()


def get_all_words():
    if cached_all_words:
        return cached_all_words

    all_entries = db_get_all_entries()
    for entry in all_entries:
        entry_text = entry.text
        if " - " in entry_text:
            word = entry_text.split(" - ")[-1]
        else:
            word = entry_text
        word = word.strip()
        if ids := cached_all_words.get(word):
            ids.append(entry.id)
        else:
            cached_all_words[word] = [entry.id]
    return cached_all_words


def get_how_long_ago(timestamp: int | None) -> str:
    if not timestamp:
        return "never"
    now = int(time.time())
    time_delta = now - timestamp

    if time_delta < 86400:
        return "<= a day "

    days = time_delta // 86400
    years = days // 365
    months = (days % 365) // 30
    remaining_days = (days % 365) % 30

    parts = []
    if years > 0:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months > 0:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if remaining_days > 0 or not parts:
        parts.append(
            f"{remaining_days} day{'s' if remaining_days != 1 else ''}"
        )

    return f"{' '.join(parts)} ago"


def build_directory_tree_markdown(
    base_path: Path, rel_url_base: str = ""
) -> str:
    markdown_lines = []
    for dirpath, dirnames, filenames in os.walk(base_path):
        dirpath = Path(dirpath)

        # Exclude hidden and unwanted directories
        dirnames[:] = [
            d for d in dirnames if not d.startswith(".") and d != "Media"
        ]

        # Filter hidden and unwanted files
        filenames = [
            f
            for f in filenames
            if not f.startswith(".")
            and not f.lower().endswith((".png", ".jpg", ".webp"))
        ]

        rel_path = dirpath.relative_to(base_path)
        indent_level = len(rel_path.parts)
        indent = "  " * indent_level

        if rel_path != Path("."):
            folder_name = dirpath.name
            header_level = min(indent_level + 2, 6)
            markdown_lines.append(f"\n{'#' * header_level} {folder_name}")

        for filename in filenames:
            file_path = (
                rel_path / filename if rel_path != Path(".") else Path(filename)
            )
            display_name = (
                filename[:-3] if filename.endswith(".md") else filename
            )
            file_url = urllib.parse.quote(
                str((Path(rel_url_base) / file_path).as_posix())
            )
            markdown_lines.append(
                f"{indent}- [{display_name}](/view_note/{file_url})"
            )

    return "\n".join(markdown_lines)


with open("config.toml", "rb") as fp:
    toml_config = tomllib.load(fp)
    NOTES_DIR = Path(toml_config["notes_folder"]).resolve()
    NOTES_DIR.mkdir(exist_ok=True)
    MW_THESAURUS_API_KEY = toml_config["mw_thesaurus_api_key"]


def safe_path_note(subpath: str) -> Path:
    """Ensure subpath is within NOTES_DIR to avoid directory traversal."""
    decoded = urllib.parse.unquote(subpath)
    final_path = (NOTES_DIR / decoded).resolve()
    if not final_path.is_relative_to(NOTES_DIR):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not final_path.exists() or not final_path.suffix == ".md":
        raise HTTPException(status_code=404, detail="Note not found")
    return final_path


@dataclass
class ThesaurusSense:
    part_of_speech: str
    meaning_html: str
    synonyms: list[str]


@dataclass
class EntryDisplay:
    entry: Entry
    text: str
    context: str
    last_review_elapsed: str


def get_synonyms(word):
    synonym = Synonyms(
        search_string=word,
        api_key=MW_THESAURUS_API_KEY,
    )
    synonyms = cast(
        list[tuple[str, str, str, list[str]]], synonym.find_synonyms()
    )
    return synonyms


def format_meaning_html(md_text: str) -> str:
    return markdown2.markdown(md_text.strip())


def get_thesaurus_senses(
    word: str,
) -> list[ThesaurusSense]:
    synonyms_data = get_synonyms(word)
    if not synonyms_data:
        return []
    senses = render_thesaurus_senses(synonyms_data)
    return senses


def render_thesaurus_senses(
    synonyms_data: list[tuple[str, str, str, list[str]]],
) -> list[ThesaurusSense]:
    senses = []
    for _, pos, meaning_md, synonyms in synonyms_data:
        meaning_html = format_meaning_html(meaning_md)
        senses.append(ThesaurusSense(pos, meaning_html, synonyms))
    return senses


def highlight_ipa(html: str) -> str:
    ipa_pattern = re.compile(
        r"(?:(?<=^)|(?<=\s))(/[^/\s<>]+?/)(?:(?=$)|(?=\s))"
    )
    soup = BeautifulSoup(html, "html.parser")

    for text_node in soup.find_all(string=True):
        parent = text_node.parent
        if parent.name in ["script", "style", "code", "pre"]:
            continue

        new_text = ipa_pattern.sub(r'<span class="ipa">\1</span>', text_node)
        text_node.replace_with(BeautifulSoup(new_text, "html.parser"))

    return str(soup)
