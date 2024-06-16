from pathlib import Path

import edge_tts
from phonemizer import phonemize
from wordhoard import Synonyms

from database import Question

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
        a = a.replace("ɹ", "r")
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
    assert isinstance(synonyms, list)
    return synonyms


def tts_edge(question: Question):
    audio_path = audio_directory / Path(f"{question.id}-edge.mp3")
    if audio_path.exists():
        return
    answer_text: str = question.answers[0].text
    tts_text: str = answer_text.split("\n")[0]
    question_sentence = question.text.split(" - ")[0]
    tts_text = f"{question_sentence}. " + tts_text
    voice = "en-US-AndrewNeural"
    communicate = edge_tts.Communicate(tts_text, voice)
    communicate.save_sync(str(audio_path))
