"""Locate the current weekly-plan PDF for each grade on a school's website.

The strategy is config-driven (see schools/*.yml): for each grade we find a
heading matching ``heading_pattern`` and then take the next link whose href
matches ``href_pattern``. This handles the common "heading then download link"
layout used by Bergen kommune school pages and is easy to extend per school.
"""
from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

USER_AGENT = ("Mozilla/5.0 (compatible; trmnl-arbeidsplan/1.0; "
              "+https://github.com/usetrmnl)")

_HEADING_TAGS = re.compile(r"^h[1-6]$")


def fetch(url: str) -> requests.Response:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp


def _abs(base: str, href: str) -> str:
    if href.startswith("http"):
        return href
    return base.rstrip("/") + "/" + href.lstrip("/")


def _extract_week(text: str) -> str:
    """'pdf Uke 26 [4.14 MB]' -> '26'; 'Uke 25 + 26' -> '25 + 26'."""
    m = re.search(r"uke\s*([0-9]+(?:\s*(?:\+|og)\s*[0-9]+)*)", text, re.I)
    return m.group(1).strip() if m else ""


def _clean_title(text: str) -> str:
    """'pdf Uke 26 [4.14 MB]' -> 'Uke 26'."""
    t = re.sub(r"\[[^\]]*\]", "", text)          # drop "[4.14 MB]"
    t = re.sub(r"^\s*pdf\b", "", t, flags=re.I)  # drop leading "pdf"
    return re.sub(r"\s+", " ", t).strip()


def _link_after_heading(soup, heading_re, href_re):
    for heading in soup.find_all(_HEADING_TAGS):
        if heading_re.search(heading.get_text(" ", strip=True)):
            for a in heading.find_all_next("a", href=True):
                if href_re.search(a["href"]):
                    return a["href"], a.get_text(" ", strip=True)
            return None
    return None


def find_plans(school: dict) -> dict:
    """Return ``{trinn: {pdf_url, trinn_label, link_text, uke, page_url}}``."""
    base = school["base_url"]
    href_re = re.compile(school["link"]["href_pattern"])
    heading_tmpl = school["link"]["heading_pattern"]

    results: dict[int, dict] = {}
    for page in school["pages"]:
        page_url = _abs(base, page["url"])
        soup = BeautifulSoup(fetch(page_url).text, "html.parser")
        for trinn in page["trinn"]:
            heading_re = re.compile(heading_tmpl.format(trinn=trinn), re.I)
            found = _link_after_heading(soup, heading_re, href_re)
            if not found:
                continue
            href, text = found
            results[trinn] = {
                "trinn": trinn,
                "trinn_label": f"{trinn}. trinn",
                "pdf_url": _abs(base, href),
                "link_text": text,
                "title": _clean_title(text),
                "uke": _extract_week(text),
                "page_url": page_url,
            }
    return results


def page_url_for(school: dict, trinn: int) -> str:
    for page in school["pages"]:
        if trinn in page["trinn"]:
            return _abs(school["base_url"], page["url"])
    return school["base_url"]
