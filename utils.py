from pathlib import Path

from phonemizer import phonemize
from wordhoard import Synonyms


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
