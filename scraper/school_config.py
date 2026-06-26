"""Load and normalise per-school scraping configs from schools/*.yml."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SCHOOLS_DIR = ROOT / "schools"


def load_schools(only=None) -> list:
    """Load every schools/*.yml, adding a derived sorted ``all_trinn`` list.

    ``only`` optionally restricts to a list of school ids.
    """
    schools = []
    for path in sorted(SCHOOLS_DIR.glob("*.yml")):
        school = yaml.safe_load(path.read_text(encoding="utf-8"))
        school.setdefault("id", path.stem)
        if only and school["id"] not in only:
            continue
        all_trinn = []
        for page in school["pages"]:
            all_trinn.extend(page["trinn"])
        school["all_trinn"] = sorted(set(all_trinn))
        school.setdefault("render", {})
        schools.append(school)
    return schools
