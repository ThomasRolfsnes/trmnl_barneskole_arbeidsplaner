#!/usr/bin/env python3
"""Scrape weekly-plan PDFs, render them to images, and write the docs/ output
served by GitHub Pages.

Run from the repo root:

    python scraper/build.py --device trmnl_x_landscape

Output per school lands in ``docs/<school>/``:
    trinn-<n>.png    rendered weekly plan (or a placeholder)
    trinn-<n>.json   merge data polled by the TRMNL plugin
    manifest.json    summary of all grades

Files are only rewritten when their content hash changes, so the ``updated``
timestamp (and thus the TRMNL screen) only moves when a new plan is published.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from devices import DEVICES
from render import RENDER_VERSION, placeholder_image, render_pdf_to_image
from scrape import fetch, find_plans, page_url_for
from school_config import load_schools

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_base_url() -> str:
    """Public base URL of the GitHub Pages site.

    Override with $PAGES_BASE_URL; otherwise derive from $GITHUB_REPOSITORY
    (owner/name -> https://owner.github.io/name). Falls back to localhost.
    """
    if os.environ.get("PAGES_BASE_URL"):
        return os.environ["PAGES_BASE_URL"].rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        # The github.io subdomain is always lowercase; the path keeps its case.
        return f"https://{owner.lower()}.github.io/{name}"
    return "http://localhost:8000"


def content_hash(*parts) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(str(part).encode("utf-8"))
    return h.hexdigest()[:12]


def read_json(path: Path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def summary(data: dict) -> dict:
    return {k: data[k] for k in
            ("trinn", "trinn_label", "available", "uke", "image_url")}


def build_school(school: dict, base_url: str, device: str,
                 dry_run: bool = False) -> dict:
    sid = school["id"]
    profile = DEVICES[device]
    page = int(school.get("render", {}).get("page", 1))
    out_dir = DOCS / sid
    out_dir.mkdir(parents=True, exist_ok=True)

    plans = find_plans(school)
    manifest = {
        "school": sid,
        "school_name": school["name"],
        "device": device,
        "source": school.get("base_url"),
        "generated": now_iso(),
        "classes": [],
    }

    for trinn in school["all_trinn"]:
        json_path = out_dir / f"trinn-{trinn}.json"
        png_path = out_dir / f"trinn-{trinn}.png"
        plan = plans.get(trinn)
        cache_key = plan["pdf_url"] if plan else "MISSING"
        chash = content_hash(cache_key, base_url, device, page, RENDER_VERSION)

        prev = read_json(json_path)
        if prev and prev.get("content_hash") == chash and png_path.exists():
            manifest["classes"].append(summary(prev))
            print(f"  {sid} trinn {trinn}: unchanged ({chash})")
            continue

        image_url = f"{base_url}/{sid}/trinn-{trinn}.png?v={chash}"
        if plan:
            print(f"  {sid} trinn {trinn}: rendering {plan['pdf_url']}")
            pdf_bytes = fetch(plan["pdf_url"]).content
            png = render_pdf_to_image(
                pdf_bytes, width=profile["width"], height=profile["height"],
                page=page, grayscale=profile["grayscale"])
            data = {
                "school": sid, "school_name": school["name"],
                "trinn": trinn, "trinn_label": plan["trinn_label"],
                "available": True,
                "uke": plan["uke"], "title": plan["title"],
                "image_url": image_url,
                "source_pdf": plan["pdf_url"], "source_page": plan["page_url"],
                "device": device, "content_hash": chash,
            }
        else:
            print(f"  {sid} trinn {trinn}: no plan found -> placeholder")
            png = placeholder_image(
                width=profile["width"], height=profile["height"],
                title=f"{trinn}. trinn",
                subtitle="Ingen arbeidsplan publisert ennå",
                grayscale=profile["grayscale"])
            data = {
                "school": sid, "school_name": school["name"],
                "trinn": trinn, "trinn_label": f"{trinn}. trinn",
                "available": False,
                "uke": "", "title": "",
                "image_url": image_url,
                "source_pdf": "", "source_page": page_url_for(school, trinn),
                "device": device, "content_hash": chash,
            }

        if not dry_run:
            png_path.write_bytes(png)
            write_json(json_path, data)
        manifest["classes"].append(summary(data))

    if not dry_run:
        write_json(out_dir / "manifest.json", manifest)
    return manifest


def write_index(manifests: list) -> None:
    sections = []
    for m in manifests:
        items = "".join(
            f'<li><a href="{m["school"]}/trinn-{c["trinn"]}.png">{c["trinn_label"]}</a>'
            f' — {"uke " + c["uke"] if c["available"] else "ingen plan"}'
            f' (<a href="{m["school"]}/trinn-{c["trinn"]}.json">json</a>)</li>'
            for c in m["classes"])
        sections.append(f"<h2>{m['school_name']}</h2><ul>{items}</ul>")
    html = (
        "<!doctype html>\n<html lang=\"no\"><head><meta charset=\"utf-8\">\n"
        "<meta name=\"robots\" content=\"noindex\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<title>Arbeidsplaner for TRMNL</title>\n"
        "<style>body{font-family:system-ui,sans-serif;max-width:720px;"
        "margin:2rem auto;padding:0 1rem;color:#222}a{color:#06c}</style>\n"
        "</head><body>\n<h1>Arbeidsplaner &rarr; TRMNL</h1>\n"
        f"<p>Automatisk genererte bilder av ukentlige arbeidsplaner. "
        f"Sist kjørt {now_iso()}.</p>\n"
        f"{''.join(sections)}\n"
        "<p style=\"color:#888;font-size:.85rem\">Kilde: skolenes egne "
        "nettsider. Bildene regenereres daglig.</p>\n</body></html>\n"
    )
    (DOCS / "index.html").write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="trmnl_x_landscape",
                        choices=list(DEVICES))
    parser.add_argument("--base-url", default=None,
                        help="public Pages base URL (default: auto-detected)")
    parser.add_argument("--school", action="append",
                        help="limit to school id(s); repeatable")
    parser.add_argument("--dry-run", action="store_true",
                        help="scrape + render but do not write files")
    args = parser.parse_args()

    base_url = (args.base_url or default_base_url()).rstrip("/")
    schools = load_schools(only=args.school)
    if not schools:
        raise SystemExit("No school configs found in schools/")

    print(f"Base URL: {base_url}   Device: {args.device}")
    manifests = []
    for school in schools:
        print(f"School: {school['name']} ({school['id']})")
        manifests.append(build_school(school, base_url, args.device, args.dry_run))
    if not args.dry_run:
        write_index(manifests)
    print("Done.")


if __name__ == "__main__":
    main()
