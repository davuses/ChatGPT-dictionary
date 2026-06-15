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

    def _query_merriam_webster(self) -> Union[List, None]:
        url = (
            f"https://www.dictionaryapi.com/api/v3/references/thesaurus/json"
            f"/{self._word}?key={self._api_key}"
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

        synonyms_data = []
        for entry in data:
            # Skip compound-word entries that don't match the searched word
            hw = entry.get("hwi", {}).get("hw", "").replace("*", "").lower()
            if hw != self._word.lower():
                continue

            pos = entry.get("fl", "")
            shortdefs = entry.get("shortdef", [])
            sseqs = (
                entry["def"][0].get("sseq", []) if entry.get("def") else []
            )

            for i, sense_group in enumerate(sseqs):
                for item in sense_group:
                    if item[0] != "sense":
                        continue
                    sense = item[1]

                    # Extract plain definition text, stripping MW markup
                    meaning = ""
                    for dt_tag, dt_content in sense.get("dt", []):
                        if dt_tag == "text":
                            meaning = regex.sub(r"\{[^}]+\}", "", dt_content).strip()
                            break
                    if not meaning and i < len(shortdefs):
                        meaning = shortdefs[i]

                    synonyms = [
                        syn["wd"]
                        for group in sense.get("syn_list", [])
                        for syn in group
                    ]

                    if synonyms:
                        synonyms_data.append([self._word, pos, meaning, synonyms])

        if synonyms_data:
            self._update_cache(synonyms=synonyms_data)
            return synonyms_data

        logger.info(f"No synonyms found for '{self._word}'")
        return None
