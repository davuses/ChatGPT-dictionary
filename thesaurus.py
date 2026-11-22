import re
import urllib.parse
from dataclasses import dataclass
from functools import lru_cache

import requests

_MW_THESAURUS_URL = (
    "https://www.dictionaryapi.com/api/v3/references/thesaurus/json/{word}?key={key}"
)
_VALID_WORD_RE = re.compile(r"^[a-zA-Z'\-\s]+$")
_MW_MARKUP_RE = re.compile(r"\{[^}]+\}")


class ThesaurusError(RuntimeError):
    """Raised when the upstream Merriam-Webster Thesaurus API cannot be reached or returns an error."""


@dataclass(frozen=True)
class ThesaurusSense:
    part_of_speech: str
    meaning: str
    synonyms: tuple[str, ...]


def _iter_senses(sseq: list):
    """Yield sense dicts from an MW sseq list, handling sense, bs, and pseq wrappers."""
    for sense_group in sseq:
        if not isinstance(sense_group, list):
            continue
        for item in sense_group:
            if not isinstance(item, list) or len(item) < 2:
                continue
            tag, body = item[0], item[1]
            if tag == "sense" and isinstance(body, dict):
                yield body
            elif tag == "bs" and isinstance(body, dict):
                sense = body.get("sense")
                if isinstance(sense, dict):
                    yield sense
            elif tag == "pseq" and isinstance(body, list):
                yield from _iter_senses([body])


@lru_cache(maxsize=512)
def fetch_thesaurus_senses(
    normalized_word: str, api_key: str
) -> tuple[ThesaurusSense, ...]:
    encoded_word = urllib.parse.quote(normalized_word, safe="")
    url = _MW_THESAURUS_URL.format(word=encoded_word, key=api_key)
    try:
        response = requests.get(url, timeout=(15, 30))
    except requests.RequestException as error:
        raise ThesaurusError("Merriam-Webster thesaurus request failed") from error

    if response.status_code != 200:
        raise ThesaurusError(
            f"Merriam-Webster thesaurus returned HTTP {response.status_code}"
        )

    try:
        data = response.json()
    except ValueError as error:
        raise ThesaurusError("Merriam-Webster thesaurus returned invalid JSON") from error

    # MW returns a list of spelling suggestions (strings) when no exact entry exists.
    if not isinstance(data, list) or not data or isinstance(data[0], str):
        return ()

    senses: list[ThesaurusSense] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        hw = entry.get("hwi", {}).get("hw", "").replace("*", "").lower()
        stems = {
            s.lower()
            for s in entry.get("meta", {}).get("stems", [])
            if isinstance(s, str)
        }
        if hw != normalized_word and normalized_word not in stems:
            continue

        pos = entry.get("fl", "")
        shortdefs = entry.get("shortdef", [])
        entry_senses_added = 0

        for def_block in entry.get("def", []):
            for i, sense in enumerate(_iter_senses(def_block.get("sseq", []))):
                meaning = ""
                for dt_entry in sense.get("dt", []):
                    if (
                        isinstance(dt_entry, list)
                        and len(dt_entry) >= 2
                        and dt_entry[0] == "text"
                        and isinstance(dt_entry[1], str)
                    ):
                        meaning = _MW_MARKUP_RE.sub("", dt_entry[1]).strip()
                        break
                if not meaning and i < len(shortdefs) and isinstance(shortdefs[i], str):
                    meaning = shortdefs[i].strip()

                seen: set[str] = set()
                synonyms: list[str] = []
                for list_key in ("syn_list", "sim_list"):
                    for group in sense.get(list_key, []):
                        for syn in group:
                            wd = syn.get("wd") if isinstance(syn, dict) else None
                            if wd and wd not in seen:
                                seen.add(wd)
                                synonyms.append(wd)

                if synonyms:
                    senses.append(ThesaurusSense(pos, meaning, tuple(synonyms)))
                    entry_senses_added += 1

        if entry_senses_added == 0:
            for i, syn_group in enumerate(entry.get("meta", {}).get("syns", [])):
                if syn_group:
                    meaning = (
                        shortdefs[i].strip()
                        if i < len(shortdefs) and isinstance(shortdefs[i], str)
                        else ""
                    )
                    senses.append(
                        ThesaurusSense(
                            pos,
                            meaning,
                            tuple(s for s in syn_group if isinstance(s, str)),
                        )
                    )

    return tuple(senses)


def lookup_thesaurus(word: str, api_key: str) -> tuple[ThesaurusSense, ...]:
    normalized = " ".join(word.split()).lower()
    if not normalized or not _VALID_WORD_RE.match(normalized):
        return ()
    clean_key = api_key.strip()
    if not clean_key:
        raise ThesaurusError("Merriam-Webster thesaurus API key is not configured")
    return fetch_thesaurus_senses(normalized, clean_key)
