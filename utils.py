from pathlib import Path


def delete_audio_file(question_id):
    audio_directory = Path("./audio")
    audio_file_path = audio_directory / f"{question_id}.mp3"
    if audio_file_path.exists():
        audio_file_path.unlink()
        print(f"Deleted {audio_file_path}")
    else:
        print(f"File {audio_file_path} doesn't exist")
