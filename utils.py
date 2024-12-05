import time
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
