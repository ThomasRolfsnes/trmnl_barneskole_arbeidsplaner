"""Locate the current weekly-plan PDF for each grade on a school's website.

Config-driven (see schools/*.yml). For each grade we build a list of candidate
PDF links, then pick the most recent one:

- ``match: heading``   — candidates are the PDF links between the grade's heading
                         (``heading_pattern``) and the next heading.
- ``match: link_text`` — candidates are PDF links whose own text matches
                         ``text_pattern`` (for pages with no per-grade headings).

``match`` and ``select`` may be set per school or overridden per page.
``require_text`` (optional) keeps only links whose text looks like a plan, so
stray links (recipes, forms, …) are ignored. ``select`` decides the winner among
candidates: ``max_week`` (default, highest parsed week number), ``first`` or
``last``.

NOTE: patterns are ``.format(trinn=...)``-substituted, so use ``{trinn}`` but
avoid regex brace quantifiers like ``{1,2}`` in the YAML patterns.
"""
from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

USER_AGENT = ("Mozilla/5.0 (compatible; trmnl-arbeidsplan/1.0; "
              "+https://github.com/usetrmnl)")

_HEADING_TAGS = re.compile(r"^h[1-6]$")
DEFAULT_HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
# A week reference: "uke"/"ukeplan" followed by one or more week numbers,
# e.g. "Ukeplan 26", "uke 25, 26", "ukeplan 25+26", "uke 25 og 26".
_WEEK_RE = re.compile(
    r"uke(?:plan)?\.?\s*([0-9]{1,2}(?:\s*(?:\+|og|,)\s*[0-9]{1,2})*)", re.I)


def fetch(url: str) -> requests.Response:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp


def _abs(base: str, href: str) -> str:
    if href.startswith("http"):
        return href
    return base.rstrip("/") + "/" + href.lstrip("/")


def _strip_size(text: str) -> str:
    return re.sub(r"\[[^\]]*\]", "", text)  # drop "[4.14 MB]"


def _week_numbers(text: str) -> list:
    nums = []
    for m in _WEEK_RE.finditer(_strip_size(text)):
        for n in re.findall(r"[0-9]{1,2}", m.group(1)):
            v = int(n)
            if 1 <= v <= 53:
                nums.append(v)
    return nums


def _week_label(text: str) -> str:
    """Human label, e.g. 'Ukeplan 25+26' -> '25 + 26'; 'Juniplan' -> ''."""
    nums = sorted(set(_week_numbers(text)))
    return " + ".join(str(n) for n in nums)


def _max_week(text: str):
    nums = _week_numbers(text)
    return max(nums) if nums else None


def _clean_title(text: str) -> str:
    """'pdf Ukeplan 26 [100 kB]' -> 'Ukeplan 26'."""
    t = _strip_size(text)
    t = re.sub(r"^\s*pdf\b", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


def _candidates_heading(soup, heading_re, boundary_re, heading_tags, href_re):
    """PDF links between the grade's heading and the next grade heading.

    A "heading" may be any tag in ``heading_tags`` — some schools mark grades up
    as <strong> rather than <h*>. The section ends at the next heading-tag
    element that either starts another grade (``boundary_re``) or is a real <h*>
    heading (e.g. a footer like "Kontakt").
    """
    head = None
    for el in soup.find_all(heading_tags):
        if heading_re.search(el.get_text(" ", strip=True)):
            head = el
            break
    if head is None:
        return []

    out = []
    for el in head.find_all_next():
        if el.name in heading_tags:
            text = el.get_text(" ", strip=True)
            is_boundary = _HEADING_TAGS.match(el.name) or (boundary_re and boundary_re.search(text))
            # A repeated heading for the SAME grade (e.g. an <h5> and a <strong>
            # both saying "5. trinn") doesn't end the section.
            if is_boundary and not heading_re.search(text):
                break
        if el.name == "a" and el.get("href") and href_re.search(el["href"]):
            out.append((el["href"], el.get_text(" ", strip=True)))
    return out


def _candidates_link_text(soup, text_re, href_re):
    """PDF links whose own text matches the grade pattern (no headings needed)."""
    out = []
    for a in soup.find_all("a", href=True):
        if href_re.search(a["href"]) and text_re.search(a.get_text(" ", strip=True)):
            out.append((a["href"], a.get_text(" ", strip=True)))
    return out


def _select(cands, mode):
    if not cands:
        return None
    if mode == "first":
        return cands[0]
    if mode == "last":
        return cands[-1]
    # max_week: highest parsed week wins; links without a week sort last; ties
    # keep document order (first seen).
    best, best_w = None, None
    for href, text in cands:
        w = _max_week(text)
        w = -1 if w is None else w
        if best is None or w > best_w:
            best, best_w = (href, text), w
    return best


def find_plans(school: dict) -> dict:
    """Return ``{trinn: {pdf_url, trinn_label, link_text, title, uke, page_url}}``."""
    base = school["base_url"]
    link = school["link"]
    href_re = re.compile(link["href_pattern"])
    require_re = re.compile(link["require_text"], re.I) if link.get("require_text") else None
    heading_tags = school.get("heading_tags", DEFAULT_HEADING_TAGS)
    boundary_re = (re.compile(link["heading_pattern"].format(trinn=r"\d+"), re.I)
                   if link.get("heading_pattern") else None)

    results: dict[int, dict] = {}
    for page in school["pages"]:
        page_url = _abs(base, page["url"])
        match = page.get("match", school.get("match", "heading"))
        select = page.get("select", school.get("select", "max_week"))
        soup = BeautifulSoup(fetch(page_url).text, "html.parser")

        for trinn in page["trinn"]:
            if match == "link_text":
                text_re = re.compile(link["text_pattern"].format(trinn=trinn), re.I)
                cands = _candidates_link_text(soup, text_re, href_re)
            else:
                heading_re = re.compile(link["heading_pattern"].format(trinn=trinn), re.I)
                cands = _candidates_heading(soup, heading_re, boundary_re, heading_tags, href_re)

            if require_re:
                cands = [c for c in cands if require_re.search(c[1])]

            chosen = _select(cands, select)
            if not chosen:
                continue
            href, text = chosen
            results[trinn] = {
                "trinn": trinn,
                "trinn_label": f"{trinn}. trinn",
                "pdf_url": _abs(base, href),
                "link_text": text,
                "title": _clean_title(text),
                "uke": _week_label(text),
                "page_url": page_url,
            }
    return results


def page_url_for(school: dict, trinn: int) -> str:
    for page in school["pages"]:
        if trinn in page["trinn"]:
            return _abs(school["base_url"], page["url"])
    return school["base_url"]
