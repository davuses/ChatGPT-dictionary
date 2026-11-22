#!/usr/bin/env python3

"""
This Python module is designed to query multiple online repositories for the
synonyms associated with the given word.
"""
__author__ = "John Bumgarner"
__date__ = "October 15, 2020"
__status__ = "Production"
__license__ = "MIT"
__copyright__ = "Copyright (C) 2020 John Bumgarner"

##################################################################################
# Date Completed: October 15, 2020
# Author: John Bumgarner
#
# Date Last Revised: May 23, 2024
# Revised by: John Bumgarner
##################################################################################

##################################################################################
# “AS-IS” Clause
#
# Except as represented in this agreement, all work produced by Developer is
# provided “AS IS”. Other than as provided in this agreement, Developer makes no
# other warranties, express or implied, and hereby disclaims all implied warranties,
# including any warranty of merchantability and warranty of fitness for a particular
# purpose.
##################################################################################

##################################################################################
# Python imports required for basic operations
##################################################################################
# Standard library imports
import logging
import re as regex
import traceback
import urllib.parse
from typing import List, Tuple, Union

# Third-party imports
import requests

from wordhoard.utilities import caching, word_verification

logger = logging.getLogger(__name__)

class Synonyms:

    def __init__(
        self,
        search_string: str = "",
        api_key: str = "",
    ):
        self._word = search_string
        self._api_key = api_key

    def _validate_word(self) -> bool:
        """
        This function is designed to validate that the syntax for
        a string variable is in an acceptable format.

        :return: True or False
        :rtype: bool
        """
        valid_word = word_verification.validate_word_syntax(self._word)
        if not valid_word:
            logger.error(f"The word {self._word} was not in a valid format.")
            logger.error(
                f"Please verify that the word {self._word} is spelled correctly."
            )
        return valid_word

    def _check_cache(self) -> Tuple[bool, Union[list, None]]:
        check_cache = caching.cache_synonyms(self._word)
        return check_cache

    def _update_cache(self, synonyms: list) -> None:
        caching.insert_word_cache_synonyms(self._word, synonyms)

    def find_synonyms(self) -> list[str | list[str]] | None:
        """
        :returns: synonym data
        :rtype: [[word: str, PoS: str, meaning: str, synonyms: list]]
        """
        if not self._validate_word():
            return None

        cache_hit, cached = self._check_cache()
        if cache_hit:
            return cached

        return self._query_merriam_webster()

    @staticmethod
    def _handle_query_exceptions(error):
        """
        Helper method to handle common exceptions in query methods.
        """
        logger.error("An error occurred in the following code segment:")
        logger.error("".join(traceback.format_tb(error.__traceback__)))

    @staticmethod
    def _iter_senses(sseq: list):
        """Yield sense dicts from an MW sseq list, handling sense, bs, and pseq wrappers."""
        for sense_group in sseq:
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
                    yield from Synonyms._iter_senses([body])

    def _query_merriam_webster(self) -> Union[List, None]:
        encoded_word = urllib.parse.quote(self._word.strip(), safe="")
        url = (
            f"https://www.dictionaryapi.com/api/v3/references/thesaurus/json"
            f"/{encoded_word}?key={self._api_key}"
        )
        try:
            response = requests.get(url, timeout=(15, 30))
        except requests.RequestException as error:
            self._handle_query_exceptions(error)
            return None

        if response.status_code != 200:
            logger.info(
                f"MW API returned status {response.status_code} for '{self._word}'"
            )
            return None

        data = response.json()

        # API returns a list of strings (spelling suggestions) when word not found
        if not data or isinstance(data[0], str):
            logger.info(f"No thesaurus entry found for '{self._word}'")
            return None

        target = self._word.strip().lower()
        synonyms_data = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            # Match either the headword or one of MW's listed stems (handles
            # inflections and phrasal entries like "zero (in on)" -> "zero in on")
            hw = entry.get("hwi", {}).get("hw", "").replace("*", "").lower()
            stems = {
                s.lower()
                for s in entry.get("meta", {}).get("stems", [])
                if isinstance(s, str)
            }
            if hw != target and target not in stems:
                continue

            pos = entry.get("fl", "")
            shortdefs = entry.get("shortdef", [])
            entry_senses_added = 0

            for def_block in entry.get("def", []):
                for i, sense in enumerate(self._iter_senses(def_block.get("sseq", []))):
                    # Extract plain definition text, stripping MW markup
                    meaning = ""
                    for dt_entry in sense.get("dt", []):
                        if (
                            isinstance(dt_entry, list)
                            and len(dt_entry) >= 2
                            and dt_entry[0] == "text"
                            and isinstance(dt_entry[1], str)
                        ):
                            meaning = regex.sub(r"\{[^}]+\}", "", dt_entry[1]).strip()
                            break
                    if not meaning and i < len(shortdefs):
                        meaning = shortdefs[i]

                    # MW Collegiate Thesaurus splits matches across syn_list
                    # ("synonyms") and sim_list ("strongest matches" / near synonyms).
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
                        synonyms_data.append([self._word, pos, meaning, synonyms])
                        entry_senses_added += 1

            # Fallback to meta.syns if def/sseq had an unexpected shape
            if entry_senses_added == 0:
                for i, syn_group in enumerate(entry.get("meta", {}).get("syns", [])):
                    if syn_group:
                        meaning = shortdefs[i] if i < len(shortdefs) else ""
                        synonyms_data.append([self._word, pos, meaning, list(syn_group)])

        if synonyms_data:
            self._update_cache(synonyms=synonyms_data)
            return synonyms_data

        logger.info(f"No synonyms found for '{self._word}'")
        return None
