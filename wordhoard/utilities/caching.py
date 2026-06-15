#!/usr/bin/env python3

"""
This Python module is to create temporary dictionary caches.  These caches are
designed to limit redundant queries.
"""
__author__ = "John Bumgarner"
__date__ = "October 15, 2020"
__status__ = "Production"
__license__ = "MIT"
__copyright__ = "Copyright (C) 2020 John Bumgarner"

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
from typing import Dict, Optional, Tuple

##################################################################################
# in memory temporary cache for synonyms
##################################################################################
temporary_dict_synonyms: Dict[str, list] = {}


def cache_synonyms(word: str) -> Tuple[bool, Optional[list]]:
    """
    Checks if the synonyms for a given word are cached in the temporary dictionary.

    :param word: The word to check for cached synonyms.
    :type word: str
    :return: A tuple indicating success (True if synonyms are cached, False otherwise) and the cached synonyms if found.
    :rtype: Tuple[bool, Optional[list]]
    """
    success = (retrieved := temporary_dict_synonyms.get(word)) is not None
    return success, retrieved


def insert_word_cache_synonyms(word: str, synonyms: list) -> None:
    """
    Inserts the cache with synonyms for a word in the temporary dictionary.

    :param word: The word to insert into the cache.
    :type word: str
    :param synonyms: The list of synonyms to cache.
    :type synonyms: list
    :return: None
    """
    if word not in temporary_dict_synonyms:
        temporary_dict_synonyms[word] = synonyms
