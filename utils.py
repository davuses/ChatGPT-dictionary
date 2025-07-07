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
from fastapi import HTTPException
from phonemizer import phonemize

from database import db_get_all_question
from wordhoard import Synonyms


def get_IPA(word) -> str:
    a = phonemize(word, strip=True, with_stress=True)
    if isinstance(a, str):
        a = a.replace("ɹ", "r").replace("ɐ", "ə")
        return a
    else:
        return str(a)


cached_all_words: dict[str, list[int]] = {}


def get_all_words():
    if cached_all_words:
        return cached_all_words

    all_questions = db_get_all_question()
    for q in all_questions:
        question_text = q.text
        if "When i ask you a word" in question_text:
            continue
        if " - " in question_text:
            word = question_text.split(" - ")[-1]
        else:
            word = question_text
        word = word.strip()
        if ids := cached_all_words.get(word):
            ids.append(q.id)
        else:
            cached_all_words[word] = [q.id]
    return cached_all_words


def from_last_visit(last_visit: int):
    ...
    now = int(time.time())
    time_delta = now - last_visit
    days = time_delta // 86400  # 86400 seconds in a day
    if days > 0:
        return f"{days} day{'s' if days > 1 else ''} ago"
    else:
        return "less than a day ago"


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
class ThesaurusEntry:
    part_of_speech: str
    meaning_html: str
    synonyms: list[str]


def get_synonyms(word):
    synonym = Synonyms(
        search_string=word,
        sources=[
            "merriam-webster",
        ],
    )
    synonyms = cast(
        list[tuple[str, str, str, list[str]]], synonym.find_synonyms()
    )
    return synonyms


def format_meaning_html(md_text: str) -> str:
    """
    Apply any custom markdown preprocessing, then convert to HTML.
    """

    # e.g. turn “as in X:Y” → italics + newline
    def repl(m: re.Match) -> str:
        a, b = m.group(1).strip(), m.group(2).strip()
        return f"as in *{a}*:\n\n{b}"

    clean_md = re.sub(r"as in (.+?):(.+)", repl, md_text.strip())
    return markdown2.markdown(clean_md)


def get_thesaurus_entries(
    word: str,
) -> list[ThesaurusEntry]:
    synonyms_data = get_synonyms(word)
    if not synonyms_data:
        return []
    entries = render_thesaurus_entries(synonyms_data)
    return entries


def render_thesaurus_entries(
    synonyms_data: list[tuple[str, str, str, list[str]]],
) -> list[ThesaurusEntry]:
    entries = []
    for _, pos, meaning_md, synonyms in synonyms_data:
        meaning_html = format_meaning_html(meaning_md)
        entries.append(ThesaurusEntry(pos, meaning_html, synonyms))
    return entries
