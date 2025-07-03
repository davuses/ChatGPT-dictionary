import os
import time
import urllib
import urllib.parse
from pathlib import Path

import edge_tts
from phonemizer import phonemize

from database import Question, db_get_all_question
from wordhoard import Synonyms

audio_directory = Path("./audio")
audio_directory.mkdir(exist_ok=True)


def delete_audio_file(question_id):
    audio_directory = Path("./audio")
    audio_file_path = audio_directory / f"{question_id}.mp3"
    if audio_file_path.exists():
        audio_file_path.unlink()
        print(f"Deleted {audio_file_path}")
    else:
        print(f"File {audio_file_path} doesn't exist")


def get_IPA(word) -> str:
    a = phonemize(word, strip=True, with_stress=True)
    if isinstance(a, str):
        a = a.replace("ɹ", "r").replace("ɐ", "ə")
        return a
    else:
        return str(a)


def get_synonyms(word):
    synonym = Synonyms(
        search_string=word,
        sources=[
            "merriam-webster",
        ],
    )
    synonyms = synonym.find_synonyms()
    return synonyms


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


def tts_edge(question: Question):
    audio_path = audio_directory / Path(f"{question.id}-edge.mp3")
    if audio_path.exists():
        return
    answer_text: str = question.answers[0].text
    tts_text: str = answer_text.split("\n")[0]
    question_sentence = question.text.split(" - ")[0]
    tts_text = f"{question_sentence}. " + tts_text
    voice = "en-US-AndrewNeural"
    communicate = edge_tts.Communicate(
        tts_text, voice, proxy="http://127.0.0.1:10802"
    )
    communicate.save_sync(str(audio_path))


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
    base_path: str, rel_url_base: str = ""
) -> str:
    markdown_lines = []
    for dirpath, dirnames, filenames in os.walk(base_path):
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

        rel_path = os.path.relpath(dirpath, base_path)
        indent_level = rel_path.count(os.sep)
        indent = "  " * indent_level

        if rel_path != ".":
            folder_name = os.path.basename(dirpath)
            header_level = min(indent_level + 2, 6)  # limit to ######
            markdown_lines.append(f"\n{'#' * header_level} {folder_name}")

        for filename in filenames:
            file_rel_path = (
                os.path.join(rel_path, filename)
                if rel_path != "."
                else filename
            )
            if filename[-3:] == ".md":
                filename = filename[:-3]  # Remove .md extension for display
            file_url = urllib.parse.quote(
                os.path.join(rel_url_base, file_rel_path).replace(os.sep, "/")
            )
            markdown_lines.append(f"{indent}- [{filename}](/notes/{file_url})")

    return "\n".join(markdown_lines)
