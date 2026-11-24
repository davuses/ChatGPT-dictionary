import math
import os
import random
import re
import threading
import time
import tomllib
import urllib.parse
from collections.abc import Collection
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString
from fastapi import HTTPException
import markdown2
from markupsafe import Markup, escape
import nh3
from phonemizer import phonemize

from database import (
    Entry,
    EntrySummary,
    db_get_all_entries,
    db_get_entry_visit_stats,
    db_get_quiz_source_entries,
)
from thesaurus import ThesaurusSense, fetch_thesaurus_senses, lookup_thesaurus


ENTRY_TEXT_SEPARATOR = " - "


def parse_entry_text(text: str) -> tuple[str, str]:
    """Split stored entry text ("<context> - <word>" or "<word>") into
    (context, word). Uses rsplit so contexts containing " - " stay intact."""
    if ENTRY_TEXT_SEPARATOR in text:
        context, word = text.rsplit(ENTRY_TEXT_SEPARATOR, 1)
        return context.strip(), word.strip()
    return "", text.strip()


def format_entry_text(word: str, context: str = "") -> str:
    """Combine word and optional context into the stored entry text format."""
    clean_word = " ".join(word.split())
    clean_context = " ".join(context.split())
    if clean_context:
        return f"{clean_context}{ENTRY_TEXT_SEPARATOR}{clean_word}"
    return clean_word


def validate_entry_fields(word: str, context: str = "") -> tuple[str | None, str | None]:
    """Validate and assemble word + optional context into single-line entry text."""
    clean_word = " ".join(word.split())
    if not clean_word:
        return None, "Word cannot be empty."
    if ENTRY_TEXT_SEPARATOR in clean_word:
        return None, 'Word cannot contain " - " (reserved as the context separator).'
    return format_entry_text(clean_word, context), None


_YOUTUBE_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    }
)
_YOUTUBE_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,}$")
_TRACKING_QUERY_PARAMS = frozenset(
    {
        "fbclid",
        "gclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "ref",
        "ref_src",
        "si",
    }
)


def normalize_page_url(raw_url: str) -> str:
    """Normalize an HTTP(S) page URL for per-page note lookup/storage.

    Canonicalizes YouTube video URLs (watch, youtu.be, shorts, live, embed,
    m., music.) to https://www.youtube.com/watch?v=<id> while leaving non-video
    YouTube pages intact. Strips fragments and common tracking parameters.
    """
    cleaned = raw_url.strip()
    parsed = urllib.parse.urlsplit(cleaned)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only http and https URLs are supported")

    host = parsed.hostname.lower()
    query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)

    if host in _YOUTUBE_HOSTS:
        video_id = ""
        path_parts = [p for p in parsed.path.split("/") if p]
        if host == "youtu.be" and path_parts:
            video_id = path_parts[0]
        elif parsed.path == "/watch":
            for k, v in query_pairs:
                if k == "v" and v:
                    video_id = v
                    break
        elif len(path_parts) >= 2 and path_parts[0] in {"shorts", "live", "embed"}:
            video_id = path_parts[1]

        if video_id and _YOUTUBE_VIDEO_ID_RE.match(video_id):
            return f"https://www.youtube.com/watch?v={video_id}"

    netloc = host
    if parsed.port is not None:
        default_port = 80 if scheme == "http" else 443
        if parsed.port != default_port:
            netloc = f"{host}:{parsed.port}"

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"

    kept_params = sorted(
        (k, v)
        for k, v in query_pairs
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_QUERY_PARAMS
    )
    query = urllib.parse.urlencode(kept_params, doseq=True)
    return urllib.parse.urlunsplit((scheme, netloc, path, query, ""))


def normalize_pronoun_casing(text: str) -> str:
    """Capitalize the standalone pronoun "i" (common in casually-typed
    source text, e.g. "i think it helps") without touching any other
    lowercase word. Display-time fix only — the stored data is left as
    saved.

    Must run before highlight_matches(), never after: this returns a plain
    str (re.sub doesn't preserve Markup), so calling it on an
    already-highlighted value would silently drop the "already escaped"
    flag and the literal <mark> tags would come out escaped on the page."""
    if not text:
        return text
    return re.sub(r"(?<!\w)i(?!\w)", "I", text)


def highlight_matches(text: str, query: str) -> Markup:
    """Wrap every case-insensitive occurrence of `query` in `text` with
    <mark>, HTML-escaping everything else. Used by /entries live search to
    show why a row matched (main.py's entries_page).

    Matches against the raw, unescaped `text` and only escapes each
    fragment while reassembling the result — escaping `text` up front and
    then regex-matching the *raw* query against the escaped string would
    silently fail to find/highlight any match that straddles an
    HTML-special character (e.g. an entry containing "&", "<", ">"): the
    row would still show up (the SQL ILIKE match runs on raw text) but
    with no highlight at all."""
    if not query:
        return escape(text)

    pattern = re.compile(re.escape(query), re.IGNORECASE)
    parts = pattern.split(text)
    matches = pattern.findall(text)

    result = escape(parts[0])
    for match, rest in zip(matches, parts[1:]):
        result += Markup("<mark>") + escape(match) + Markup("</mark>") + escape(rest)
    return result


_ipa_lock = threading.Lock()
_words_cache_lock = threading.Lock()
_quiz_pool_lock = threading.Lock()


@lru_cache(maxsize=2048)
def get_IPA(word: str) -> str:
    # libespeak-ng is not thread-safe, so serialize phonemize() on cache misses.
    with _ipa_lock:
        a = phonemize(word, strip=True, with_stress=True)
    if isinstance(a, str):
        return a.replace("ɹ", "r").replace("ɐ", "ə")
    return str(a)


_cached_all_words: dict[int, dict[str, list[int]]] = {}


def invalidate_words_cache(user_id: int | None = None) -> None:
    with _words_cache_lock:
        if user_id is None:
            _cached_all_words.clear()
        else:
            _cached_all_words.pop(user_id, None)


def get_all_words(user_id: int) -> dict[str, list[int]]:
    with _words_cache_lock:
        cached = _cached_all_words.get(user_id)
        if cached is not None:
            return cached
        words: dict[str, list[int]] = {}
        for entry in db_get_all_entries(user_id):
            _, word = parse_entry_text(entry.text)
            key = word.lower()
            if not key:
                continue
            if ids := words.get(key):
                ids.append(entry.id)
            else:
                words[key] = [entry.id]
        _cached_all_words[user_id] = words
        return words


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
    Require enough surrounding context beyond the headword itself so a
    multi-word entry never blanks out the entire sentence."""
    if not _word_in_text(word, text):
        return False
    min_words = max(QUIZ_MIN_SENTENCE_WORDS, len(word.split()) + 3)
    return len(text.split()) >= min_words


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

# A whole line wrapped in a single pair of asterisks ("*fit in with*") is
# markdown italic emphasis used as a sub-heading grouping the quotes below
# it, not a sentence — distinct from a real bullet marker ("* content"),
# which has a space right after the asterisk.
_WHOLE_LINE_ITALIC_LABEL_RE = re.compile(r"^\*[^*\s].*[^*\s]\*$")
_BULLET_LINE_RE = re.compile(r"^\*\s")


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
        if len(lines) == 1 and _WHOLE_LINE_ITALIC_LABEL_RE.match(lines[0]) and not _BULLET_LINE_RE.match(lines[0]):
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


_cached_quiz_pool: dict[int, list[QuizCandidate]] = {}


def invalidate_quiz_pool_cache(user_id: int | None = None) -> None:
    with _quiz_pool_lock:
        if user_id is None:
            _cached_quiz_pool.clear()
        else:
            _cached_quiz_pool.pop(user_id, None)


def get_quiz_pool(user_id: int) -> list[QuizCandidate]:
    """Entries quizzable with a plain fill-in-the-blank: the headword must
    appear as a whole word in the entry's own context clause and/or its
    example. Entries without a clean match are left out rather than
    guessed at (no stemming, no LLM-generated sentences)."""
    with _quiz_pool_lock:
        cached = _cached_quiz_pool.get(user_id)
        if cached is not None:
            return cached
        pool: list[QuizCandidate] = []
        for entry_id, entry_text, entry_example in db_get_quiz_source_entries(user_id):
            context, word = parse_entry_text(entry_text)
            if not word:
                continue

            sentences = [
                s for s in _example_sentences(entry_example)
                if _is_quizzable_sentence(word, s)
            ]
            if context and _is_quizzable_sentence(word, context):
                sentences.insert(0, context)
            if sentences:
                pool.append(
                    QuizCandidate(entry_id=entry_id, word=word, sentences=sentences)
                )
        _cached_quiz_pool[user_id] = pool
        return pool


QUIZ_UNSEEN_BASE_WEIGHT = 4.5
QUIZ_MAX_RECENCY_FACTOR = 6.0
QUIZ_RECENT_COOLDOWN_FACTOR = 0.1
QUIZ_RECENT_COOLDOWN_SECONDS = 86400


def _quiz_weight(visit_count: int, last_visit: int | None, now: int) -> float:
    """Weight a quiz candidate so unvisited and long-neglected entries surface
    more often while every entry keeps a positive weight.

    - Anything visited (or newly created) within the last 24h gets a strong
      cooldown so it doesn't bounce right back.
    - All visit_count == 0 entries past that cooldown share one high baseline
      weight, avoiding a mismatch between legacy rows (last_visit=None) and
      entries added via the UI (last_visit=created_at).
    - Previously visited entries decay by visit_count and grow smoothly with
      log1p(days since last visit).
    """
    visits = max(visit_count, 0)
    if last_visit is not None:
        elapsed = max(0, now - last_visit)
        if elapsed < QUIZ_RECENT_COOLDOWN_SECONDS:
            return QUIZ_RECENT_COOLDOWN_FACTOR / (1.0 + visits)
        if visits == 0:
            return QUIZ_UNSEEN_BASE_WEIGHT
        days = elapsed / 86400
        recency_factor = min(math.log1p(days), QUIZ_MAX_RECENCY_FACTOR)
    else:
        if visits == 0:
            return QUIZ_UNSEEN_BASE_WEIGHT
        recency_factor = QUIZ_UNSEEN_BASE_WEIGHT

    visit_factor = 1.0 / ((1.0 + visits) ** 1.5)
    return visit_factor * recency_factor


def _pick_weighted_candidate(
    pool: list[QuizCandidate],
    visit_stats: dict[int, tuple[int, int | None]],
    exclude_entry_ids: Collection[int] = frozenset(),
    *,
    now: int | None = None,
    rng: random.Random = random,
) -> QuizCandidate | None:
    active_pool = [c for c in pool if c.entry_id in visit_stats]
    if not active_pool:
        return None
    excluded = set(exclude_entry_ids)
    candidates = [c for c in active_pool if c.entry_id not in excluded] or active_pool
    current_time = int(time.time()) if now is None else now
    weights = [
        _quiz_weight(*visit_stats[c.entry_id], now=current_time)
        for c in candidates
    ]
    return rng.choices(candidates, weights=weights, k=1)[0]


def _question_from_candidate(candidate: QuizCandidate, rng: random.Random) -> QuizQuestion:
    sentence = normalize_pronoun_casing(rng.choice(candidate.sentences))
    blanked_sentence, display_word = _blank_word(sentence, candidate.word)
    return QuizQuestion(
        entry_id=candidate.entry_id,
        word=display_word,
        blanked_sentence=blanked_sentence,
    )


def pick_random_question(
    user_id: int,
    exclude_entry_ids: Collection[int] = frozenset(),
) -> QuizQuestion | None:
    pool = get_quiz_pool(user_id)
    if not pool:
        return None
    visit_stats = db_get_entry_visit_stats(user_id)
    candidate = _pick_weighted_candidate(pool, visit_stats, exclude_entry_ids)
    if not candidate:
        return None
    return _question_from_candidate(candidate, random)


def get_how_long_ago(timestamp: int | None, now: int | None = None) -> str:
    if not timestamp:
        return "never"
    current_time = int(time.time()) if now is None else now
    time_delta = max(0, current_time - timestamp)

    if time_delta < 60:
        return "just now"
    if time_delta < 3600:
        minutes = time_delta // 60
        return f"{minutes} min ago"
    if time_delta < 86400:
        hours = time_delta // 3600
        return f"{hours} hour{'s' if hours != 1 else ''} ago"

    days = time_delta // 86400
    years = days // 365
    months = (days % 365) // 30
    remaining_days = (days % 365) % 30

    parts = []
    if years > 0:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months > 0:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if years == 0 and (remaining_days > 0 or not parts):
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
            safe_label = (
                display_name.replace("\\", "\\\\")
                .replace("[", "\\[")
                .replace("]", "\\]")
            )
            file_url = urllib.parse.quote(
                str((Path(rel_url_base) / file_path).as_posix())
            )
            markdown_lines.append(
                f"{indent}- [{safe_label}](/view_note/{file_url})"
            )

    return "\n".join(markdown_lines)


CONFIG_PATH = Path(__file__).with_name("config.toml")


@lru_cache
def _load_app_config() -> dict[str, object]:
    try:
        with CONFIG_PATH.open("rb") as fp:
            return tomllib.load(fp)
    except FileNotFoundError as error:
        raise RuntimeError(f"Missing configuration file: {CONFIG_PATH}") from error
    except tomllib.TOMLDecodeError as error:
        raise RuntimeError("config.toml contains invalid TOML") from error


@lru_cache
def get_notes_dir() -> Path:
    config = _load_app_config()
    raw_folder = config.get("notes_folder")
    if not isinstance(raw_folder, str) or not raw_folder.strip():
        raise RuntimeError("notes_folder in config.toml must be a non-empty string")
    folder = Path(raw_folder)
    if not folder.is_absolute():
        folder = CONFIG_PATH.parent / folder
    notes_dir = folder.resolve()
    notes_dir.mkdir(exist_ok=True)
    return notes_dir


@lru_cache
def get_mw_thesaurus_api_key() -> str:
    config = _load_app_config()
    api_key = config.get("mw_thesaurus_api_key", "")
    if not isinstance(api_key, str):
        raise RuntimeError("mw_thesaurus_api_key in config.toml must be a string")
    return api_key


def safe_path_note(subpath: str) -> Path:
    """Ensure subpath is within the configured notes directory to avoid directory traversal."""
    notes_dir = get_notes_dir()
    final_path = (notes_dir / subpath).resolve()
    if not final_path.is_relative_to(notes_dir):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not final_path.exists() or not final_path.suffix == ".md":
        raise HTTPException(status_code=404, detail="Note not found")
    return final_path


@dataclass
class EntryDisplay:
    entry: Entry | EntrySummary
    text: str
    context: str


def clear_thesaurus_cache() -> None:
    fetch_thesaurus_senses.cache_clear()


def get_thesaurus_senses(word: str) -> list[ThesaurusSense]:
    return list(lookup_thesaurus(word, get_mw_thesaurus_api_key()))


def get_thesaurus_senses_plain(word: str) -> tuple[dict[str, object], ...]:
    """Plain-text thesaurus senses for JSON API consumers (backed by thesaurus cache)."""
    senses = lookup_thesaurus(word, get_mw_thesaurus_api_key())
    return tuple(
        {
            "part_of_speech": sense.part_of_speech,
            "meaning": sense.meaning,
            "synonyms": list(sense.synonyms),
        }
        for sense in senses
    )


_SAFE_MARKDOWN_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "del",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "strong",
    "sub",
    "sup",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}
_SAFE_MARKDOWN_ATTRIBUTES = {
    "a": {"href", "title"},
    "th": {"align"},
    "td": {"align"},
}
_SAFE_URL_SCHEMES = {"http", "https", "mailto"}


def render_safe_markdown(
    text: str, *, extras: list[str] | None = None, wrap_ipa: bool = False
) -> str:
    """Render user-authored Markdown to sanitized HTML via nh3.

    Sanitization runs *before* highlight_ipa() so untrusted Markdown cannot
    inject arbitrary attributes/classes while highlight_ipa() can safely add
    `<span class="ipa">` around text-node IPA transcripts.
    """
    raw_html = markdown2.markdown(text, extras=extras or ["strike"])
    clean_html = nh3.clean(
        raw_html,
        tags=_SAFE_MARKDOWN_TAGS,
        attributes=_SAFE_MARKDOWN_ATTRIBUTES,
        url_schemes=_SAFE_URL_SCHEMES,
    )
    if wrap_ipa:
        return highlight_ipa(clean_html)
    return clean_html


def highlight_ipa(html: str) -> str:
    ipa_pattern = re.compile(
        r"(?:(?<=^)|(?<=\s))(/[^/\s<>]+?/)(?:(?=$)|(?=\s))"
    )
    soup = BeautifulSoup(html, "html.parser")

    for text_node in list(soup.find_all(string=True)):
        parent = text_node.parent
        if parent and parent.name in {"script", "style", "code", "pre"}:
            continue

        raw_text = str(text_node)
        if not ipa_pattern.search(raw_text):
            continue

        nodes = []
        last_end = 0
        for match in ipa_pattern.finditer(raw_text):
            if match.start() > last_end:
                nodes.append(NavigableString(raw_text[last_end : match.start()]))
            span = soup.new_tag("span", attrs={"class": "ipa"})
            span.string = match.group(1)
            nodes.append(span)
            last_end = match.end()
        if last_end < len(raw_text):
            nodes.append(NavigableString(raw_text[last_end:]))
        text_node.replace_with(*nodes)

    return str(soup)
