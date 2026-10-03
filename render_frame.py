"""Annual country-board renderer for Visual Spec v1 (coordinates in pixels)."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping

from PIL import Image, ImageDraw, ImageFont
from project_paths import ROOT, recorded_path


# Explicit row delimiters preserve commas that are part of country names.
COUNTRY_ROWS = (
    "Afghanistan|Albania|Algeria|Andorra|Angola|Antarctica|Argentina|Armenia|Australia|Austria|Azerbaijan|Bahamas, The|Bahrain|Bangladesh|Barbados|Belarus",
    "Belize|Benin|Bhutan|Bolivia|Bosnia and H.|Botswana|Brazil|Brunei|Bulgaria|Burkina Faso|Burundi|Cabo Verde|Cambodia|Cameroon|Canada|Central African Rep.",
    "Chad|Chile|China|Colombia|Comoros|Congo, DR|Congo, R|Costa Rica|Croatia|Cuba|Cyprus|Czechia|Côte d'Ivoire|Denmark|Djibouti|Dominica",
    "Dominican Republic|Ecuador|Egypt, Arab Rep.|El Salvador|Equatorial Guinea|Eritrea|Estonia|eSwatini|Ethiopia|Fiji|Finland|France|Gabon|Gambia, The|Georgia|Germany",
    "Ghana|Greece|Grenada|Guatemala|Guinea|Guinea-Bissau|Guyana|Haiti|Honduras|Hungary|Iceland|India|Indonesia|Iran, Islamic Rep.|Iraq|Ireland",
    "Israel|Italy|Jamaica|Japan|Jordan|Kazakhstan|Kenya|Kiribati|Korea, DPR|Korea|Kosovo|Kuwait|Kyrgyz Republic|Lao PDR|Latvia|Lebanon",
    "Lesotho|Liberia|Libya|Liechtenstein|Lithuania|Luxembourg|Macedonia, FYR|Madagascar|Malawi|Malaysia|Maldives|Mali|Malta|Marshall Islands|Mauritania|Mauritius",
    "Mexico|Micronesia|Moldova|Monaco|Mongolia|Montenegro|Morocco|Mozambique|Myanmar|Namibia|Nauru|Nepal|Netherlands|New Zealand|Nicaragua|Niger",
    "Nigeria|Norway|Oman|Pakistan|Palau|Panama|Papua New Guinea|Paraguay|Peru|Philippines|Poland|Portugal|Qatar|Romania|Russia|Rwanda",
    "Samoa|San Marino|Sao Tome and P.|Saudi Arabia|Senegal|Seychelles|Sierra Leone|Singapore|Slovak Republic|Slovenia|Solomon Islands|Somalia|South Africa|South Sudan|Spain|Sri Lanka",
    "St. Kitts and Nevis|St. Lucia|St. V. and the G.|Sudan|Suriname|Sweden|Switzerland|Syria|Taiwan|Tajikistan|Thailand|Timor-Leste|Togo|Tonga|Trinidad and Tobago|Tunisia",
    "Turkey|Turkmenistan|Tuvalu|Uganda|Ukraine|United Arab Emirates|Uruguay|USA|Uzbekistan|Vanuatu|Venezuela, RB|Vietnam|Yemen, Rep.|Zambia|Zimbabwe",
)
COUNTRY_ORDER = tuple(name for row in COUNTRY_ROWS for name in row.split("|"))
COLOR_ANCHORS = (
    (-2.0, (0x45, 0x75, 0xB7)),
    (-1.0, (0xA8, 0xD2, 0xE8)),
    (0.0, (0xF7, 0xF9, 0xC7)),
    (1.0, (0xFE, 0xB0, 0x5D)),
    (2.0, (0xE1, 0x42, 0x29)),
)


@dataclass(frozen=True)
class RenderConfig:
    """Tunable v1 parameters; sizes are final-image pixels, not points."""

    supersampling: int = 3
    x0: float = 97.8
    y0: float = 185.9
    dx: float = 114.4
    dy: float = 68.6
    radius_scale: float = 39.2
    minimum_radius: float = 2.5
    edge_width: float = 1.25
    title_size: int = 53
    year_size: int = 106
    label_size: int = 17
    value_size: int = 16
    footer_size: int = 16
    text_outline_width: float = 1.5
    title_font: str | None = None
    label_font: str | None = None
    footer_font: str | None = None
    show_values: bool = True
    title_end_year: int = 2025
    credit_line: str = "Extended through 2025"

    def __post_init__(self):
        if type(self.title_end_year) is not int or not 1880 <= self.title_end_year <= 2025:
            raise ValueError("title_end_year must be an integer in 1880–2025")
        if type(self.supersampling) is not int or not 1 <= self.supersampling <= 4:
            raise ValueError("supersampling must be an integer from 1 to 4")
        for name in ("x0", "y0", "dx", "dy", "radius_scale", "minimum_radius",
                     "edge_width", "title_size", "year_size", "label_size",
                     "value_size", "footer_size", "text_outline_width"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")


def grid_xy(index: int, config: RenderConfig | None = None) -> tuple[float, float]:
    """Slot 191 exists geometrically but is deliberately never populated."""
    if type(index) is not int or not 0 <= index < 192:
        raise ValueError("grid index must be an integer from 0 to 191")
    cfg = config or RenderConfig()
    return cfg.x0 + index % 16 * cfg.dx, cfg.y0 + index // 16 * cfg.dy


def bubble_radius(anomaly: float, config: RenderConfig | None = None) -> float:
    if not math.isfinite(anomaly):
        raise ValueError("bubble anomaly must be finite")
    cfg = config or RenderConfig()
    return max(cfg.minimum_radius, cfg.radius_scale * math.sqrt(abs(anomaly)))


def anomaly_color(anomaly: float) -> tuple[int, int, int]:
    if not math.isfinite(anomaly):
        raise ValueError("color anomaly must be finite")
    value = min(2.0, max(-2.0, anomaly))
    for (low, color_low), (high, color_high) in zip(COLOR_ANCHORS, COLOR_ANCHORS[1:]):
        if value <= high:
            fraction = (value - low) / (high - low)
            return tuple(round(a + fraction * (b - a)) for a, b in zip(color_low, color_high))
    return COLOR_ANCHORS[-1][1]


def format_anomaly(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "N/A"
    if not math.isfinite(value):
        raise ValueError("infinite anomalies are invalid")
    # Avoid a misleading '-0.0' after display rounding.
    rounded = round(value, 1)
    return f"{0.0 if rounded == 0 else rounded:+.1f}°C"


def resolve_font(role: str, explicit: str | None = None) -> str:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"Font does not exist: {path}")
        return str(path)
    root = Path(__file__).parent / "assets" / "fonts"
    win = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates = {
        "title": [root / "DejaVuSans.ttf", root / "Oswald-Regular.ttf", root / "RobotoCondensed-Regular.ttf",
                  win / "ARIALN.TTF", Path("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf")],
        "label": [root / "DejaVuSans-Bold.ttf", root / "Lato-Bold.ttf", Path("/usr/share/fonts/truetype/lato/Lato-Bold.ttf"),
                  win / "arialbd.ttf", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")],
        "footer": [root / "DejaVuSans.ttf", root / "Lato-Regular.ttf", Path("/usr/share/fonts/truetype/lato/Lato-Regular.ttf"),
                   win / "arial.ttf", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")],
    }
    for path in candidates[role]:
        if path.is_file():
            return str(path.resolve())
    raise ValueError(f"No usable {role} font; supply --{role}-font PATH")


@lru_cache(maxsize=128)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _validated_values(values: Mapping[str, float | None]) -> dict[str, float | None]:
    unknown = set(values) - set(COUNTRY_ORDER)
    if unknown:
        raise ValueError(f"Unknown country labels: {', '.join(sorted(unknown))}")
    result = {}
    for country in COUNTRY_ORDER:
        value = values.get(country)
        if value is not None:
            if isinstance(value, (str, bool)):
                raise ValueError(f"{country}: anomaly must be numeric or None")
            value = float(value)
            if math.isinf(value):
                raise ValueError(f"{country}: infinite anomaly")
            if math.isnan(value):
                value = None
        result[country] = value
    return result


def render_frame(year: int, values: Mapping[str, float | None], *,
                 config: RenderConfig | None = None,
                 source_lines: tuple[str, ...] | None = None,
                 year_label: str | None = None) -> Image.Image:
    """Return a 1920×1080 RGB frame. Missing countries remain visible as N/A.

    The renderer consumes annual values; it does not validate their scientific
    provenance, monthly completeness, baseline or geographic aggregation.
    """
    if type(year) is not int or not 1880 <= year <= 2025:
        raise ValueError("year must be an integer in 1880–2025")
    cfg = config or RenderConfig()
    data = _validated_values(values)
    s = cfg.supersampling
    canvas = Image.new("RGB", (1920 * s, 1080 * s), "#F7F7F7")
    draw = ImageDraw.Draw(canvas)
    paths = {role: resolve_font(role, getattr(cfg, f"{role}_font"))
             for role in ("title", "label", "footer")}

    def text(x, y, content, size, role="label", anchor="mm", fill="#161616", outline=False):
        draw.text((x * s, y * s), content, font=_font(paths[role], round(size * s)),
                  fill=fill, anchor=anchor,
                  stroke_width=round(cfg.text_outline_width * s) if outline else 0,
                  stroke_fill="#333333" if outline else None)

    def circle(x, y, value):
        radius = bubble_radius(value, cfg)
        draw.ellipse(((x - radius) * s, (y - radius) * s,
                      (x + radius) * s, (y + radius) * s),
                     fill=anomaly_color(value), outline="#B8B8B8",
                     width=max(1, round(cfg.edge_width * s)))

    title_size = cfg.title_size
    while _font(paths["title"], round(title_size * s)).getlength("Temperature Anomalies by Country") > 820 * s:
        title_size -= 1
    text(13, 12, "Temperature Anomalies by Country", title_size, "title",
         anchor="lt", fill="#D0D0D0", outline=True)
    text(13, 65, f"Years 1880 - {cfg.title_end_year}", title_size, "title",
         anchor="lt", fill="#D0D0D0", outline=True)
    label = str(year) if year_label is None else year_label
    year_size = cfg.year_size
    while _font(paths["title"], round(year_size * s)).getlength(label) > 500 * s:
        year_size -= 1
    text(990, 55, label, year_size, "title", fill="#D0D0D0", outline=True)

    draw.rectangle((1370 * s, 1 * s, 1890 * s, 125 * s), outline="#777777", width=s)
    for x, value in zip((1427, 1528, 1630, 1732, 1833), (-2.0, -1.0, 0.0, 1.0, 2.0)):
        circle(x, 63, value)
        text(x, 63, format_anomaly(value), cfg.value_size)

    # All circles precede all labels, so overlapping bubbles cannot hide text.
    for index, country in enumerate(COUNTRY_ORDER):
        if data[country] is not None:
            circle(*grid_xy(index, cfg), data[country])
    for index, country in enumerate(COUNTRY_ORDER):
        x, y = grid_xy(index, cfg)
        # Fit long names on the fixed board without changing their spelling.
        size = cfg.label_size
        while _font(paths["label"], round(size * s)).getlength(country) > (cfg.dx - 6) * s:
            size -= 0.25
            if size <= 8:
                break
        text(x, y - 10 if cfg.show_values else y, country, size)
        if cfg.show_values:
            text(x, y + 12, format_anomaly(data[country]), cfg.value_size)

    missing = sum(value is None for value in data.values())
    if source_lines is None:
        source_lines = (
            "Data Source:",
            "NASA GISS, GISTEMP Land-Ocean Temperature Index (LOTI), ERSSTv5, 1200km smoothing",
            "https://data.giss.nasa.gov/gistemp/",
            "Average of monthly temperature anomalies. GISTEMP base period 1951–1980.",
        )
    for i, line in enumerate(source_lines):
        text(14, 1005 + i * 18, line, cfg.footer_size, "footer", anchor="lt", fill="#404040")
    credits = (
        "Visual reference: Antti Lipponen (@anttilip), Flickr CC BY 2.0",
        "Based on original visualization by Antti Lipponen",
        "Visual by Attila Mielec",
        cfg.credit_line,
        f"Missing annual values: {missing}/191 (N/A)" if missing else "Annual temperature anomalies (°C)",
    )
    for i, line in enumerate(credits):
        text(1906, 987 + i * 18, line, cfg.footer_size, "footer", anchor="rt", fill="#404040")
    return canvas.resize((1920, 1080), Image.Resampling.LANCZOS)


def load_annual_csv(path: Path) -> dict[int, dict[str, float | None]]:
    """Strict long CSV: country,year,anomaly_c; empty/NA/N/A/NaN = missing.

    Extra provenance columns are allowed. Exact Visual Spec country names are
    required; duplicate rows, unknown countries and out-of-scope years fail.
    """
    data: dict[int, dict[str, float | None]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"country", "year", "anomaly_c"}.issubset(reader.fieldnames or []):
            raise ValueError("CSV requires country,year,anomaly_c columns")
        for line, row in enumerate(reader, 2):
            try:
                country = row["country"].strip()
                year = int(row["year"])
                raw = row["anomaly_c"].strip()
                if country not in COUNTRY_ORDER:
                    raise ValueError(f"unknown country {country!r}")
                if not 1880 <= year <= 2025:
                    raise ValueError("year outside 1880–2025")
                if country in data.get(year, {}):
                    raise ValueError(f"duplicate country-year: {country}, {year}")
                value = None if raw.lower() in ("", "na", "n/a", "nan") else float(raw)
                if value is not None and not math.isfinite(value):
                    raise ValueError("anomaly must be finite or missing")
                data.setdefault(year, {})[country] = value
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError(f"CSV line {line}: {exc}") from exc
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--csv", type=Path, help="annual long CSV: country,year,anomaly_c")
    input_group.add_argument("--layout-preview", action="store_true", help="no data: all countries show N/A")
    input_group.add_argument("--lipponen-csv", type=Path, help="historical wide CSV for visual calibration only")
    parser.add_argument("--years", nargs="+", type=int, default=[1890, 1896, 1905])
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output/frames")
    parser.add_argument("--supersampling", type=int, default=3)
    parser.add_argument("--comparison-style", action="store_true", help="historical 2017 subtitle and country names without numbers")
    for role in ("title", "label", "footer"):
        parser.add_argument(f"--{role}-font")
    args = parser.parse_args()
    try:
        cfg = RenderConfig(supersampling=args.supersampling, title_font=args.title_font,
                           label_font=args.label_font, footer_font=args.footer_font,
                           show_values=not args.comparison_style,
                           title_end_year=2017 if args.comparison_style else 2025)
        if any(not 1880 <= year <= 2025 for year in args.years):
            raise ValueError("requested years must be in 1880–2025")
        reference_report = None
        if args.lipponen_csv:
            from reference_data import load_lipponen_csv
            data, reference_report = load_lipponen_csv(args.lipponen_csv)
        else:
            data = {} if args.layout_preview else load_annual_csv(args.csv)
        if not args.layout_preview and any(year not in data for year in args.years):
            raise ValueError("CSV has no rows for one or more requested years")
        paths = {role: resolve_font(role, getattr(cfg, f"{role}_font"))
                 for role in ("title", "label", "footer")}
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for year in dict.fromkeys(args.years):
            values = data.get(year, {})
            sources = ("Layout preview — no annual dataset supplied.",
                       "All country anomalies are unavailable (N/A).",
                       "Visual Spec v1; 1951–1980 baseline intended for actual data.") if args.layout_preview else None
            if args.lipponen_csv:
                sources = ("Calibration data: Antti Lipponen, supplied Tdata.csv (1880–2019).",
                           "Historical reference only; not the recalculated 1880–2025 dataset.",
                           "Missing countries remain N/A; supplied country names mapped explicitly.")
            frame = render_frame(year, values, config=cfg, source_lines=sources)
            mode = "layout-preview" if args.layout_preview else "reference" if args.lipponen_csv else "frame"
            stem = f"{mode}{'-comparison' if args.comparison_style else ''}-{year}"
            destination = args.output_dir / f"{stem}.png"
            frame.save(destination)
            metadata = {
                "year": year, "mode": mode,
                "input_csv": recorded_path(args.csv or args.lipponen_csv) if args.csv or args.lipponen_csv else None,
                "reference_report": reference_report,
                "scientific_validation": "not performed by renderer",
                "missing_countries": [c for c in COUNTRY_ORDER if values.get(c) is None],
                "fonts": {role: recorded_path(path) for role, path in paths.items()},
                "config": {key: recorded_path(value) if key.endswith("_font") and value else value
                           for key, value in asdict(cfg).items()}, "country_order": COUNTRY_ORDER,
                "size": [1920, 1080], "display_precision": "signed, one decimal °C",
            }
            destination.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(destination)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
