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
import sys
import traceback
from typing import Dict, List, Optional, Tuple, Union

# Third-party imports
import bs4
import requests
from bs4 import BeautifulSoup

from wordhoard.utilities import caching, word_verification
from wordhoard.utilities.cloudflare_checker import CloudflareVerification

# Local or project-specific imports
from wordhoard.utilities.request_html import Query

logger = logging.getLogger(__name__)


class ParseWords:
    """
    This utility class contains static methods to parse synonyms from HTML responses of various sources,
    which are Collins Dictionary, Merriam-Webster, Synonym.com, Thesaurus.com, and WordNet.

    Methods
    -------
    _handle_query_exceptions(error):
        Helper method to handle common exceptions in query methods.

    parse_collins_dictionary(soup: BeautifulSoup) -> list:
        Parses synonyms from the HTML response of Collins Dictionary.

    parse_merriam_webster(soup: BeautifulSoup) -> list:
        Parses synonyms from the HTML response of Merriam-Webster.

    parse_synonym_com(soup: BeautifulSoup) -> list:
        Parses synonyms from the HTML response of Synonym.com.

    parse_thesaurus_com(soup: BeautifulSoup) -> list:
        Parses synonyms from the HTML response of Thesaurus.com.

    parse_wordnet(soup: BeautifulSoup) -> list:
        Parses synonyms from the HTML response of WordNet.
    """

    @staticmethod
    def _handle_query_exceptions(error):
        """
        Helper method to handle common exceptions in query methods.
        """
        logger.error("An error occurred in the following code segment:")
        logger.error("".join(traceback.format_tb(error.__traceback__)))

    @staticmethod
    def parse_merriam_webster_modified(soup: BeautifulSoup) -> list:
        synonyms_data: list = []
        # [hword, pos, meaning, synonyms_list]
        try:
            if thesaurus_entries := soup.select(
                selector="div.entry-word-section-container"
            ):
                for thesaurus_entry in thesaurus_entries:
                    hword, PoS = "", ""
                    if header := thesaurus_entry.find(
                        name="p", attrs={"class": "hword"}
                    ):
                        hword = header.text.split()[0]
                    if PoS_h2 := thesaurus_entry.find(
                        name="h2", attrs={"class": "parts-of-speech"}
                    ):
                        PoS = PoS_h2.text.strip()
                    if sub_thesaurus_entries := thesaurus_entry.find_all(
                        name="div", attrs={"class": "vg-sseq-entry-item"}
                    ):
                        for sub_thesaurus_entry in sub_thesaurus_entries:
                            as_in_word = sub_thesaurus_entry.find(
                                name="div", attrs={"class": "as-in-word"}
                            ).text
                            definition = (
                                sub_thesaurus_entry.find(
                                    name="span", attrs={"class": "dt"}
                                )
                                .text.strip()
                                .split("\n")[0]
                                .strip()
                            )
                            meaning = ": ".join([as_in_word, definition])
                            synonyms_list = []
                            if word_container := sub_thesaurus_entry.find(
                                name="div",
                                attrs={
                                    "class": "thes-list-content synonyms_list"
                                },
                            ):
                                for list_item in word_container.find_all(
                                    name="li",
                                    attrs={"class": "thes-word-list-item"},
                                ):
                                    if (
                                        list_item.find(
                                            name="span",
                                            attrs={"class": "lozenge color-4"},
                                        )
                                        or list_item.find(
                                            name="span",
                                            attrs={"class": "lozenge color-3"},
                                        )
                                        or list_item.find(
                                            name="span",
                                            attrs={"class": "lozenge color-2"},
                                        )
                                    ):
                                        link = list_item.find(
                                            name="a", href=True
                                        )
                                        synonyms_list.append(
                                            link.text.strip().lower()
                                        )
                            synonyms_data.append(
                                [hword, PoS, meaning, synonyms_list]
                            )
        except (
            bs4.FeatureNotFound,
            AttributeError,
            IndexError,
            KeyError,
            TypeError,
        ) as error:
            ParseWords._handle_query_exceptions(error)
        return synonyms_data


class Synonyms:
    """
    A Python class for querying multiple online repositories to find synonyms for a specific word.

    Usage Examples
    ----------
    >>> synonym = Synonyms('mother')
    >>> results = synonym.find_synonyms()

    Parameters
    ----------
    search_string : str, optional
        The word for which synonyms are to be found.
    sources: Optional[List[str]]
        The sources to search for synonyms.
    output_format : str, optional
        Format for returned results. Default is 'list'. Acceptable values are 'dictionary', 'list', or 'json'.
    max_number_of_requests : int, optional
        Maximum number of requests within a specified time period.
    rate_limit_timeout_period : int, optional
        Time period before temporary hibernation due to rate limiting.
    user_agent : str, optional
        User agent string for HTTP requests.
    proxies : dict, optional
        Dictionary of proxies for Python Requests.

    Attributes
    ----------
    _proxies : Optional[Dict[str, str]]
        Proxies to use with Python Requests.
    _word : str
        The word to find synonyms for.
    _sources : Optional[List[str]]
        The sources to search for synonyms.
    _user_agent : Optional[str]
        User agent for HTTP requests.
    _output_format : str
        Format for returned results.
    _valid_output_formats : Set[str]
        Set of valid output formats.
    _rate_limit_status : bool
        Status indicating whether rate limit is reached.

    Methods
    -------
    find_synonyms() -> Union[List[Sized], Dict[str, List[str]], str]:
        Finds synonyms for the specified word.
    _validate_word() -> bool:
        Validates the syntax of the word.
    _check_cache() -> Tuple[bool, Union[Dict[str, List[str]], None]]:
        Checks if synonyms are cached.
    _update_cache(pos_category: str, synonyms: Union[List[str], Set[str]]) -> None:
        Updates the cache with new synonyms.
    _request_http_response(url: str) -> requests.models.Response:
        Makes an HTTP request and returns the response.
    _run_query_tasks_in_parallel() -> List[tuple[List[str], str]]:
        Runs query tasks in parallel using a ThreadPool.
     _query_output(self, antonyms: list, part_of_speech: Union[set[str], str]) -> Union[list, dict, str]:
        Process the output format based on the specified format.
    _handle_query_exceptions(error):
        Handles common exceptions in query methods.
    _query_collins_dictionary() -> Union[Tuple[List[str], str], None]:
        Queries collinsdictionary.com for synonyms.
    _query_merriam_webster() -> Union[Tuple[List[str], str], None]:
        Queries merriam-webster.com for synonyms.
    _query_synonym_com() -> Union[Tuple[List[str], str], None]:
        Queries synonym.com for synonyms.
    _query_thesaurus_com() -> Union[Tuple[List[str], str], None]:
        Queries thesaurus.com for synonyms.
    _query_wordnet() -> Union[Tuple[List[str], str], None]:
        Queries wordnet for synonyms.
    """

    def __init__(
        self,
        search_string: str = "",
        sources: Optional[List[str]] = None,
        output_format: str = "list",
        max_number_of_requests: int = 30,
        rate_limit_timeout_period: int = 60,
        user_agent: Optional[str] = None,
        proxies: Optional[Dict[str, str]] = None,
    ):

        self._proxies = proxies
        self._word = search_string
        self._user_agent = user_agent
        self._output_format = output_format
        self._valid_output_formats = {"dictionary", "list", "json"}
        self._sources = sources

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

    def _request_http_response(self, url: str) -> requests.models.Response:
        """
        This function queries the requested online repository and returns the
        response for this specific query.

        :param url: the URL for the online repository being queried
        :return: response content
        :rtype: requests.models.Response
        """
        response = None
        if self._proxies is None and self._user_agent is None:
            response = Query(url).get_website_html()
        elif self._proxies is None and self._user_agent is not None:
            response = Query(url, self._user_agent).get_website_html()
        elif self._proxies is not None and self._user_agent is None:
            response = Query(
                url, user_agent=None, proxies=self._proxies
            ).get_website_html()
        elif self._proxies is not None and self._user_agent is not None:
            response = Query(
                url, user_agent=self._user_agent, proxies=self._proxies
            ).get_website_html()
        return response

    def find_synonyms(self) -> list[str | list[str]] | None:
        """
        :returns: synonym data
        :rtype: [[word: str, PoS: str, meaning: str, synonyms: list]]
        """

        if self._output_format not in self._valid_output_formats:
            print(
                f"The provided output type --> {self._output_format} <-- is not one of the "
                f"acceptable types: dictionary, list or json."
            )
            sys.exit(1)
        else:
            valid_word = self._validate_word()
            if valid_word is False:
                print(
                    f"Please verify that the word {self._word} is spelled correctly."
                )
            elif valid_word is True:
                check_cache = self._check_cache()
                if check_cache[0] is True:

                    synonyms_results = check_cache[1]
                    return synonyms_results

                elif check_cache[0] is False:
                    synonyms_results = self._query_merriam_webster()
                    if not synonyms_results:
                        print(
                            f"No synonyms were found for the word: {self._word} \n"
                            f"Please verify that the word is spelled correctly."
                        )
                    else:
                        return synonyms_results

    @staticmethod
    def _handle_query_exceptions(error):
        """
        Helper method to handle common exceptions in query methods.
        """
        logger.error("An error occurred in the following code segment:")
        logger.error("".join(traceback.format_tb(error.__traceback__)))

    def _query_merriam_webster(self) -> Union[List, None]:
        """
        This function queries merriam-webster.com for synonyms associated
        with the specific word provided to the Class Synonyms.

        :returns: list of synonyms and part of speech string or NoneType
        :rtype: Union[Tuple[List[str], str], None]
        :raises:
            - AttributeError: When an attribute reference or assignment fails.
            - IndexError: When a sequence subscript is out of range.
            - KeyError: When a mapping key is not found in the set of existing keys.
            - TypeError: When an operation or function is applied to an inappropriate type.
            - bs4.FeatureNotFound: Raised by the BeautifulSoup constructor if no parser with the requested features is found.
        """
        try:
            response = self._request_http_response(
                url=f"https://www.merriam-webster.com/thesaurus/{self._word}"
            )

            if response.status_code == 404:
                logger.info(
                    f"Merriam-webster.com had no synonym reference for the word {self._word}"
                )
                return None

            soup_object = BeautifulSoup(markup=response.text, features="lxml")
            cloudflare_protection = CloudflareVerification(
                url="https://www.merriam-webster.com", soup=soup_object
            ).cloudflare_protected_url()

            if cloudflare_protection is False:
                pattern = regex.compile(pattern=r"Words fail us")
                if soup_object.find(text=pattern):
                    logger.info(
                        f"Merriam-webster.com had no synonym reference for the word {self._word}"
                    )
                    return None

                elif soup_object.find(
                    name="h1", attrs={"class": "mispelled-word"}
                ):
                    logger.info(
                        f"Merriam-webster.com had no synonym reference for the word {self._word}"
                    )
                    return None

                synonyms_data = ParseWords.parse_merriam_webster_modified(
                    soup=soup_object
                )
                # part_of_speech_category = PartOfSpeech.part_of_speech_category_merriam_webster(soup=soup_object)
                if synonyms_data:
                    self._update_cache(synonyms=synonyms_data)
                    return synonyms_data
                else:
                    logger.info(
                        f"Merriam-webster.com had no synonym reference for the word {self._word}"
                    )
                    return None
            elif cloudflare_protection is True:
                return None
        except (
            bs4.FeatureNotFound,
            AttributeError,
            IndexError,
            KeyError,
            TypeError,
        ) as error:
            self._handle_query_exceptions(error)
