import os
import random
import re
import time
import tomllib
import urllib
import urllib.parse
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import cast

import markdown2
from bs4 import BeautifulSoup
from fastapi import HTTPException
from phonemizer import phonemize

from database import Entry, EntrySummary, db_get_all_entries
from wordhoard import Synonyms


def normalize_pronoun_casing(text: str) -> str:
    """Capitalize the standalone pronoun "i" (common in casually-typed
    source text, e.g. "i think it helps") without touching any other
    lowercase word. Display-time fix only — the stored data is left as
    saved."""
    if not text:
        return text
    return re.sub(r"(?<!\w)i(?!\w)", "I", text)


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


QUIZ_MIN_SENTENCE_WORDS = 5


def _word_in_text(word: str, text: str | None) -> bool:
    """Whole-word (not substring) case-insensitive match, e.g. "cat" must not
    match inside "category"."""
    if not text:
        return False
    pattern = r"(?<!\w)" + re.escape(word) + r"(?!\w)"
    return re.search(pattern, text, re.IGNORECASE) is not None


def _is_quizzable_sentence(word: str, text: str | None) -> bool:
    """Whole-word match is necessary but not sufficient: some "examples"
    are really just usage notes or alternate phrasings ("Or well-balanced",
    "grind away at*"), too short to give a test-taker enough to work with.
    Require a minimum amount of surrounding context."""
    return _word_in_text(word, text) and len(text.split()) >= QUIZ_MIN_SENTENCE_WORDS


def _blank_word(sentence: str, word: str) -> tuple[str, str]:
    """Blank every occurrence, not just the first — a sentence can
    legitimately use the same word twice (e.g. two clauses joined into one
    quote), and leaving a second instance visible would give the answer
    away.

    Returns (blanked_sentence, display_word). The display word is taken
    from how it actually appears in the sentence, not from the entry's
    stored headword — entries are saved as "<context> - <word>" and the
    two aren't always cased the same (e.g. word stored as "Pipe dream"
    when the sentence has lowercase "pipe dream"), which would otherwise
    make a perfectly ordinary word look like a proper noun on reveal.
    """
    pattern = re.compile(r"(?<!\w)" + re.escape(word) + r"(?!\w)", re.IGNORECASE)
    match = pattern.search(sentence)
    display_word = match.group(0) if match else word
    return pattern.sub("_____", sentence), display_word


# Lexicographic metadata labels seen in this data ("Related: rosy, ...",
# "ADJ: ...", "SYN: pillage, plunder"), as opposed to a real sentence.
# Deliberately a specific denylist rather than a general "Word:" pattern —
# some paragraphs are legitimate speaker-attributed quotes ("Jack Barsky:
# KGB Spy, I threw myself into..."), which a blanket pattern would wrongly
# discard too.
_NON_SENTENCE_LABEL_RE = re.compile(
    r"^(related|also(?:\s+verb)?|noun|adj|verb|syn(?:onyms?)?|adv|opp|"
    r"origin|plural|pronunciation|note|easily confused|always plural|"
    r"generally|figuratively)\s*:",
    re.IGNORECASE,
)


def _example_sentences(example: str | None) -> list[str]:
    """Split an Entry.example field into individual candidate sentences.

    Many entries store a single plain sentence, but a majority store a
    whole markdown blob instead: a leading gloss/definition line followed
    by several quoted usage examples (each paragraph prefixed with "> "
    or "* "). Only the quoted usage paragraphs make good quiz material —
    the leading gloss is a definition, not a sentence to blank — so quote
    paragraphs are extracted individually and preferred; the raw field is
    only used as-is when it has no such structure at all. Paragraphs that
    are themselves lexicographic labels/notes, not sentences, are dropped
    regardless.
    """
    if not example:
        return []
    example = example.strip()
    if not example:
        return []

    paragraphs = re.split(r"\r?\n\s*\r?\n", example)
    quote_paragraphs = []
    plain_paragraphs = []
    for para in paragraphs:
        lines = [line.strip() for line in para.strip().splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            continue
        is_quote = all(line.startswith((">", "*")) for line in lines)
        cleaned = " ".join(line.lstrip("> *").strip() for line in lines).strip()
        if not cleaned or _NON_SENTENCE_LABEL_RE.match(cleaned):
            continue
        (quote_paragraphs if is_quote else plain_paragraphs).append(cleaned)

    return quote_paragraphs or plain_paragraphs


@dataclass(frozen=True)
class QuizCandidate:
    entry_id: int
    word: str
    sentences: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class QuizQuestion:
    entry_id: int
    word: str
    blanked_sentence: str


cached_quiz_pool: list[QuizCandidate] = []


def invalidate_quiz_pool_cache() -> None:
    cached_quiz_pool.clear()


def get_quiz_pool() -> list[QuizCandidate]:
    """Entries quizzable with a plain fill-in-the-blank: the headword must
    appear as a whole word in the entry's own context clause and/or its
    example. Entries without a clean match are left out rather than
    guessed at (no stemming, no LLM-generated sentences)."""
    if cached_quiz_pool:
        return cached_quiz_pool

    for entry in db_get_all_entries():
        if " - " not in entry.text:
            continue
        context, word = entry.text.rsplit(" - ", 1)
        word = word.strip()
        if not word:
            continue

        sentences = [
            s for s in _example_sentences(entry.example)
            if _is_quizzable_sentence(word, s)
        ]
        if _is_quizzable_sentence(word, context):
            sentences.insert(0, context)
        if sentences:
            cached_quiz_pool.append(
                QuizCandidate(entry_id=entry.id, word=word, sentences=sentences)
            )

    return cached_quiz_pool


def _question_from_candidate(candidate: QuizCandidate, rng: random.Random) -> QuizQuestion:
    sentence = normalize_pronoun_casing(rng.choice(candidate.sentences))
    blanked_sentence, display_word = _blank_word(sentence, candidate.word)
    return QuizQuestion(
        entry_id=candidate.entry_id,
        word=display_word,
        blanked_sentence=blanked_sentence,
    )


def pick_random_question(exclude_entry_id: int | None = None) -> QuizQuestion | None:
    pool = get_quiz_pool()
    if not pool:
        return None
    candidates = [c for c in pool if c.entry_id != exclude_entry_id] or pool
    return _question_from_candidate(candidates[random.randrange(len(candidates))], random)


def pick_daily_question() -> QuizQuestion | None:
    """Same question all day (and for every session that day), seeded by
    today's date so it acts like a lightweight daily prompt."""
    pool = get_quiz_pool()
    if not pool:
        return None
    rng = random.Random(date.today().isoformat())
    candidate = pool[rng.randrange(len(pool))]
    return _question_from_candidate(candidate, rng)


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
    entry: Entry | EntrySummary
    text: str
    context: str


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
