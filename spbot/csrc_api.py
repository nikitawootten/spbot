"""
This file provides an API to retrieve publications from NIST's CSRC website.
"""

import json
import os
import time
from typing import TypedDict, Dict, Optional
import logging

import requests
from requests.adapters import HTTPAdapter
from lxml import html
from urllib3.util import Retry

from spbot.common import CACHE_DIR


logger = logging.getLogger(__name__)


API_BASE_URL = "https://csrc.nist.gov"
API_SP_LIST_URL = API_BASE_URL + "/publications/sp"


class PublicationOverview(TypedDict):
    "Information contained within the CSRC publication listing."
    series: str
    number: str
    status: str
    release_date: str
    title: str
    href: str


def list_publications(
    session: Optional[requests.Session] = None,
) -> Dict[str, PublicationOverview]:
    """
    :return: A dictionary of publication overviews, keyed by the publication identifier.
    """
    response = None
    if session:
        response = session.get(API_SP_LIST_URL)
    else:
        response = requests.get(API_SP_LIST_URL)

    page = html.fromstring(response.content)
    results_table_items = page.xpath(
        "//table[@id='publications-results-table']/tbody/tr"
    )

    sps = {}
    for result in results_table_items:
        series = result.xpath("td[starts-with(@id, 'pub-series-')]/text()")[0].strip()
        number = result.xpath("td[starts-with(@id, 'pub-number-')]/text()")[0].strip()
        status = result.xpath("td[starts-with(@id, 'pub-status-')]/text()")[0].strip()
        release_date = result.xpath("td[starts-with(@id, 'pub-release-date-')]/text()")[
            0
        ].strip()

        title = result.xpath(".//a[starts-with(@id, 'pub-title-link-')]/text()")[
            0
        ].strip()
        href = result.xpath(".//a[starts-with(@id, 'pub-title-link-')]/@href")[
            0
        ].strip()

        sps[f"{series} {number}"] = {
            "series": series,
            "number": number,
            "status": status,
            "release_date": release_date,
            "title": title,
            "href": API_BASE_URL + href,
        }

    return sps


class PublicationDetails(PublicationOverview):
    "Contains PublicationOverview enriched with information from the publication page."
    publication_links: list[str]


def enrich_publication_overview(
    overview: PublicationOverview, session: Optional[requests.Session] = None
) -> PublicationDetails:
    details: PublicationDetails = {**overview, "publication_links": []}

    response = None
    if session:
        response = session.get(overview["href"])
    else:
        response = requests.get(overview["href"])
    page = html.fromstring(response.content)

    links = page.xpath("//a[@id='pub-local-download-link']/@href")

    # Replace relative links with absolute links
    # (os.path.dirname is a terrible kludge, but it works!)
    links = [
        (os.path.dirname(response.url) + link) if link.startswith("/") else link
        for link in links
    ]

    details["publication_links"] = links
    return details


class PublicationResolver:
    "Wraps the basic CSRC API with a caching layer."

    PUBLICATIONS_CACHE_KEY = "publications.json"
    INDEX_CACHE_KEY = "index.json"
    FILES_CACHE_DIR = "files"

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or self._build_session()

    def _build_session(self, total=5, backoff_factor=0.2):
        # Used https://www.zenrows.com/blog/python-requests-retry as a reference
        retry_strategy = Retry(
            total=total,
            backoff_factor=backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)

        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def list_documents(self, sleep_time=0) -> Dict[str, PublicationDetails]:
        publication_cache_path = os.path.join(CACHE_DIR, self.PUBLICATIONS_CACHE_KEY)
        if os.path.isfile(publication_cache_path):
            logger.debug(
                "Publications cache hit", extra={"cache_path": publication_cache_path}
            )
            with open(publication_cache_path, "r") as f:
                return json.load(f)

        overview = list_publications(session=self.session)

        details = {}
        for key, value in overview.items():
            logger.debug("Fetching publication details", extra={"key": key})
            details[key] = enrich_publication_overview(value, session=self.session)
            if sleep_time > 0:
                time.sleep(sleep_time)

        logger.debug(
            "Updating publications cache", extra={"cache_path": publication_cache_path}
        )
        os.makedirs(os.path.dirname(publication_cache_path), exist_ok=True)
        with open(publication_cache_path, "w") as f:
            json.dump(details, f)

        return details

    def get_cached_publication_file(self, href: str) -> Optional[str]:
        """
        Manages downloading and caching of publication files.

        Returns the path to the cached file.
        """

        index = {}
        index_cache_path = os.path.join(CACHE_DIR, self.INDEX_CACHE_KEY)
        if os.path.isfile(index_cache_path):
            with open(index_cache_path, "r") as f:
                index = json.load(f)

        if href in index:
            return index[href]

        response = self.session.get(href)
        file_cache_path = None
        if response.status_code == 200:
            filename = response.url.replace("://", "_").replace("/", "_")
            file_cache_path = os.path.join(CACHE_DIR, self.FILES_CACHE_DIR, filename)
            os.makedirs(os.path.dirname(file_cache_path), exist_ok=True)
            with open(file_cache_path, "wb") as f:
                f.write(response.content)

        index[href] = file_cache_path
        with open(index_cache_path, "w") as f:
            os.makedirs(os.path.dirname(index_cache_path), exist_ok=True)
            json.dump(index, f)

        return file_cache_path
