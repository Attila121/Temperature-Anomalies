"""Explicit adapter for the supplied historical validation table."""

import csv
import math
from pathlib import Path

from render_frame import COUNTRY_ORDER

ALIASES = {
    "Bahamas": "Bahamas, The", "Bosnia and Herzegovina": "Bosnia and H.",
    "Central African Republic": "Central African Rep.",
    "Dem. Rep. Congo": "Congo, DR", "Rep. Congo": "Congo, R",
    "C�te d'Ivoire": "Côte d'Ivoire", "Egypt": "Egypt, Arab Rep.",
    "Gambia": "Gambia, The", "Iran": "Iran, Islamic Rep.",
    "Korea, Dem. Rep.": "Korea, DPR", "Korea, Rep.": "Korea",
    "Russian Federation": "Russia", "Sao Tome and Principe": "Sao Tome and P.",
    "St. Vincent and the Grenadines": "St. V. and the G.",
    "United States of America": "USA", "Venezuela": "Venezuela, RB",
    "Yemen": "Yemen, Rep.",
}


def load_lipponen_csv(path: Path):
    data = {}
    present, excluded, applied = set(), [], {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"Country", "ISOA3", "Continent"}.issubset(reader.fieldnames or []):
            raise ValueError("Lipponen CSV requires Country,ISOA3,Continent columns")
        years = [int(name) for name in reader.fieldnames if name.isdecimal()]
        if not years or any(not 1880 <= year <= 2025 for year in years):
            raise ValueError("missing or out-of-scope reference year columns")
        for line, row in enumerate(reader, 2):
            source_name = row["Country"]
            country = ALIASES.get(source_name, source_name)
            if country not in COUNTRY_ORDER:
                if source_name not in ("Belgium", "United Kingdom"):
                    raise ValueError(f"CSV line {line}: unmapped country {source_name!r}")
                excluded.append(source_name)
                continue
            if country in present:
                raise ValueError(f"CSV line {line}: duplicate reference country {country}")
            present.add(country)
            if country != source_name:
                applied[source_name] = country
            for year in years:
                raw = row[str(year)].strip()
                value = None if raw.lower() in ("", "na", "n/a", "nan") else float(raw)
                if value is not None and not math.isfinite(value):
                    raise ValueError(f"CSV line {line}: nonfinite anomaly")
                data.setdefault(year, {})[country] = value
    return data, {"years": [min(years), max(years)], "mapped_countries": len(present),
                  "missing_layout_countries": [c for c in COUNTRY_ORDER if c not in present],
                  "excluded_source_countries": excluded, "aliases_applied": applied}
