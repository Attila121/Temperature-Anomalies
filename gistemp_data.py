"""Derive fixed-boundary country annual anomalies from the supplied GISTEMP grid."""

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np
import shapely
from shapely import STRtree, box, make_valid, segmentize
from shapely.geometry import shape
from shapely.ops import transform, unary_union

from netcdf_reader import ClassicHeader
from project_paths import ROOT, recorded_path
from reference_data import load_lipponen_csv
from render_frame import COUNTRY_ORDER, load_annual_csv

SOURCE = ROOT / "data/raw/gistemp1200_GHCNv4_ERSSTv5.nc.gz"
GEOMETRY = ROOT / "data/raw/ne_10m_admin_0_countries.geojson"
ANNUAL = ROOT / "data/derived/country-anomalies-gistemp-1880-2025.csv"
RECOMPUTED = ROOT / "output/country-anomalies-gistemp-1880-2025.csv"
GEOMETRY_URL = "https://github.com/nvkelso/natural-earth-vector/blob/v5.1.2/geojson/ne_10m_admin_0_countries.geojson"
GEOMETRY_BLOB = "5ebc66e25fc1af01edaebe9375c546655e04cf1e"
RADIUS_KM = 6371.0088

# Codes follow the fixed 191-slot board. XKX is the explicit Kosovo identifier.
COUNTRY_ISO3 = dict(zip(COUNTRY_ORDER, """
AFG ALB DZA AND AGO ATA ARG ARM AUS AUT AZE BHS BHR BGD BRB BLR
BLZ BEN BTN BOL BIH BWA BRA BRN BGR BFA BDI CPV KHM CMR CAN CAF
TCD CHL CHN COL COM COD COG CRI HRV CUB CYP CZE CIV DNK DJI DMA
DOM ECU EGY SLV GNQ ERI EST SWZ ETH FJI FIN FRA GAB GMB GEO DEU
GHA GRC GRD GTM GIN GNB GUY HTI HND HUN ISL IND IDN IRN IRQ IRL
ISR ITA JAM JPN JOR KAZ KEN KIR PRK KOR XKX KWT KGZ LAO LVA LBN
LSO LBR LBY LIE LTU LUX MKD MDG MWI MYS MDV MLI MLT MHL MRT MUS
MEX FSM MDA MCO MNG MNE MAR MOZ MMR NAM NRU NPL NLD NZL NIC NER
NGA NOR OMN PAK PLW PAN PNG PRY PER PHL POL PRT QAT ROU RUS RWA
WSM SMR STP SAU SEN SYC SLE SGP SVK SVN SLB SOM ZAF SSD ESP LKA
KNA LCA VCT SDN SUR SWE CHE SYR TWN TJK THA TLS TGO TON TTO TUN
TUR TKM TUV UGA UKR ARE URY USA UZB VUT VEN VNM YEM ZMB ZWE
""".split(), strict=True))


def checksum(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def decode_anomalies(packed, attrs):
    """Mask packed fill values before converting temperature differences to °C."""
    values = packed.astype(np.float64)
    valid = np.isfinite(values)
    for key in ("_FillValue", "missing_value"):
        for missing in attrs.get(key, []):
            valid &= packed != missing
    if attrs.get("units") not in ("K", "degC", "degrees_Celsius"):
        raise ValueError("unexpected anomaly units")
    values = values * attrs.get("scale_factor", [1])[0] + attrs.get("add_offset", [0])[0]
    values[~valid] = np.nan
    # Kelvin and Celsius differences are equal; do not subtract 273.15.
    return values


def read_gistemp(path):
    with gzip.open(path, "rb") as handle:
        header = ClassicHeader(handle.read())
    if "Base: 1951-1980" not in header.attributes.get("history", ""):
        raise ValueError("GISTEMP snapshot must identify the 1951–1980 baseline")
    times, attrs = header.read_vector("time")
    match = re.fullmatch(r"days since (\d{4})-(\d{1,2})-(\d{1,2})(?:.*)", attrs.get("units", ""))
    if not match or attrs.get("calendar", "standard") not in ("standard", "gregorian", "proleptic_gregorian"):
        raise ValueError("unsupported time coordinate")
    origin = dt.datetime(*map(int, match.groups()))
    all_dates = [origin + dt.timedelta(days=float(t)) for t in times]
    selected = [i for i, d in enumerate(all_dates) if 1880 <= d.year <= 2025]
    dates = [all_dates[i] for i in selected]
    if [(d.year, d.month) for d in dates] != [(y, m) for y in range(1880, 2026) for m in range(1, 13)]:
        raise ValueError("input must contain exactly one chronological observation for each month of 1880–2025")
    lat, _ = header.read_vector("lat")
    lon, _ = header.read_vector("lon")
    if not np.array_equal(lat, np.arange(-89, 90, 2)) or not np.array_equal(lon, np.arange(-179, 180, 2)):
        raise ValueError("expected ascending GISTEMP 2° grid cell centres")
    var = next(v for v in header.variables if v["name"] == "tempanomaly")
    if [header.dimensions[i]["name"] for i in var["dimension_ids"]] != ["time", "lat", "lon"]:
        raise ValueError("expected tempanomaly(time, lat, lon)")
    packed, anomaly_attrs = header.read_array("tempanomaly")
    values = decode_anomalies(packed[selected], anomaly_attrs).reshape(len(dates), -1)
    if values.shape != (1752, 16200):
        raise ValueError("unexpected monthly grid shape")
    return values, lat, lon, {"attributes": header.attributes, "anomaly_attributes": anomaly_attrs,
                            "first_month": dates[0].strftime("%Y-%m"), "last_month": dates[-1].strftime("%Y-%m"),
                            "snapshot_last_month": all_dates[-1].strftime("%Y-%m")}


def equal_area_geometry(geometry):
    """Spherical cylindrical equal-area coordinates, with 0.1° edge densification."""
    return make_valid(transform(lambda x, y, z=None: (
        RADIUS_KM * np.deg2rad(x), RADIUS_KM * np.sin(np.deg2rad(y))),
        segmentize(geometry, max_segment_length=0.1)))


def country_geometries(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    groups, continents = {}, {}
    # Retain the board's countries, merging the two separately mapped de facto
    # entities into their parent ISO countries; Kosovo remains its own slot.
    overrides = {"KOS": "XKX", "SOL": "SOM", "CYN": "CYP"}
    for feature in payload["features"]:
        props = feature["properties"]
        code = overrides.get(props["ADM0_A3"], props["ISO_A3_EH"])
        if code not in COUNTRY_ISO3.values():
            continue
        geom = make_valid(shape(feature["geometry"]))
        if geom.is_empty:
            raise ValueError(f"empty country geometry: {code}")
        groups.setdefault(code, []).append(geom)
        continents[code] = props["CONTINENT"]
    missing = set(COUNTRY_ISO3.values()) - groups.keys()
    if missing:
        raise ValueError(f"country polygons are missing: {sorted(missing)}")
    return {c: unary_union(groups[code]) for c, code in COUNTRY_ISO3.items()}, continents


def overlap_weights(geometry, cells, tree):
    """Fractional overlap areas; includes countries smaller than a grid cell."""
    projected = equal_area_geometry(geometry)
    indices = tree.query(projected, predicate="intersects")
    areas = shapely.area(shapely.intersection(projected, cells[indices]))
    usable = areas > 0
    indices, areas = indices[usable], areas[usable]
    if not len(indices) or not np.isclose(areas.sum(), projected.area, rtol=1e-6):
        raise ValueError(f"grid intersections must cover the entire country geometry: {areas.sum()} / {projected.area} km²")
    order = np.argsort(indices)
    return indices[order], areas[order]


def monthly_country(values, indices, areas, minimum_coverage=0.0):
    """Renormalize area weights over available cells and report area coverage."""
    subset = values[:, indices]
    valid = np.isfinite(subset)
    represented = valid @ areas
    coverage = np.clip(represented / areas.sum(), 0, 1)
    monthly = np.full(len(values), np.nan)
    usable = (represented > 0) & (coverage >= minimum_coverage)
    monthly[usable] = (np.where(valid, subset, 0) @ areas)[usable] / represented[usable]
    return monthly, coverage


def complete_annual(monthly):
    months = np.asarray(monthly).reshape(-1, 12)
    complete = np.isfinite(months).all(axis=1)
    annual = np.full(len(months), np.nan)
    annual[complete] = months[complete].mean(axis=1)
    return annual, (~np.isfinite(months)).sum(axis=1)


def comparison_metrics(actual, reference):
    a, b = np.array(actual), np.array(reference)
    delta = a - b
    return {"n": len(a), "mae_c": float(np.abs(delta).mean()),
            "rmse_c": float(np.sqrt(np.mean(delta ** 2))), "bias_c": float(delta.mean()),
            "correlation": float(np.corrcoef(a, b)[0, 1]) if len(a) > 1 and a.std() > 0 and b.std() > 0 else None}


def validate_reference(annual, path):
    reference, mapping = load_lipponen_csv(path)
    per_country, all_actual, all_reference = {}, [], []
    for ci, country in enumerate(COUNTRY_ORDER):
        pairs = [(annual[y - 1880, ci], reference[y].get(country)) for y in reference
                 if np.isfinite(annual[y - 1880, ci]) and reference[y].get(country) is not None]
        if pairs:
            actual, historical = map(list, zip(*pairs))
            per_country[country] = comparison_metrics(actual, historical)
            all_actual.extend(actual)
            all_reference.extend(historical)
    return {"source": recorded_path(path), "sha256": checksum(path), "mapping": mapping,
            "overall": comparison_metrics(all_actual, all_reference), "per_country": per_country,
            "interpretation": "Diagnostic comparison across different GISTEMP snapshots and aggregation methods; no numerical acceptance threshold was specified."}


def derive_dataset(source=SOURCE, geometry=GEOMETRY, output=RECOMPUTED, minimum_coverage=0.0, reference=None):
    if not math.isfinite(minimum_coverage) or not 0 <= minimum_coverage <= 1:
        raise ValueError("minimum coverage must be between 0 and 1")
    values, lat, lon, source_info = read_gistemp(source)
    geometries, continents = country_geometries(geometry)
    # Promote the packed float32 coordinates before projection so adjacent
    # cell edges meet exactly instead of leaving metre-scale numeric gaps.
    x = RADIUS_KM * np.deg2rad(lon.astype(np.float64))
    bottom = RADIUS_KM * np.sin(np.deg2rad(lat.astype(np.float64) - 1))
    top = RADIUS_KM * np.sin(np.deg2rad(lat.astype(np.float64) + 1))
    half_width = RADIUS_KM * np.deg2rad(1)
    cells = np.array([box(cx - half_width, low, cx + half_width, high)
                      for low, high in zip(bottom, top) for cx in x], dtype=object)
    tree = STRtree(cells)
    annual = np.full((146, 191), np.nan)
    monthly = np.full((1752, 191), np.nan)
    coverage = np.zeros_like(monthly)
    missing_months = np.zeros((146, 191), dtype=int)
    spatial = {}
    weight_matrix = np.zeros((191, 16200))
    for ci, country in enumerate(COUNTRY_ORDER):
        try:
            indices, areas = overlap_weights(geometries[country], cells, tree)
        except ValueError as exc:
            raise ValueError(f"{country}: {exc}") from exc
        weight_matrix[ci, indices] = areas
        monthly[:, ci], coverage[:, ci] = monthly_country(values, indices, areas, minimum_coverage)
        annual[:, ci], missing_months[:, ci] = complete_annual(monthly[:, ci])
        spatial[country] = {"iso3": COUNTRY_ISO3[country], "continent": continents[COUNTRY_ISO3[country]],
                            "n_grid_cells": len(indices), "effective_area_km2": float(areas.sum())}
        if ci % 20 == 0:
            print(f"Aggregated {ci + 1}/191 countries: {country}", flush=True)
    # These assertions gate export and the final video, separately from the
    # historical diagnostic comparison which has no agreed tolerance.
    if not np.array_equal(np.isfinite(annual), missing_months == 0):
        raise ValueError("annual completeness validation failed")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    columns = ["country", "iso3", "continent", "year", "anomaly_c", "coverage_fraction",
               "minimum_monthly_coverage_fraction", "missing_months", "n_grid_cells",
               "effective_area_km2", "quality_flag", "source", "dataset_version", "geometry_version"]
    snapshot_hash, geometry_hash = checksum(source), checksum(geometry)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for yi, year in enumerate(range(1880, 2026)):
            for ci, country in enumerate(COUNTRY_ORDER):
                month_coverage = coverage[yi * 12:(yi + 1) * 12, ci]
                valid = np.isfinite(annual[yi, ci])
                writer.writerow({"country": country, **spatial[country], "year": year,
                    "anomaly_c": f"{annual[yi, ci]:.8f}" if valid else "N/A",
                    "coverage_fraction": f"{month_coverage.mean():.8f}",
                    "minimum_monthly_coverage_fraction": f"{month_coverage.min():.8f}",
                    "missing_months": int(missing_months[yi, ci]),
                    "quality_flag": "missing_months" if not valid else "complete" if month_coverage.min() >= 1 - 1e-8 else "partial_spatial_coverage",
                    "source": "NASA GISTEMP v4 LOTI ERSSTv5 1200km", "dataset_version": snapshot_hash,
                    "geometry_version": geometry_hash})
    # Read through the renderer's strict CSV validator before publication.
    loaded = load_annual_csv(output)
    if sorted(loaded) != list(range(1880, 2026)) or any(set(v) != set(COUNTRY_ORDER) for v in loaded.values()):
        raise ValueError("exported dataset failed country/year validation")
    np.savez_compressed(output.with_suffix(".monthly.npz"), monthly_anomaly_c=monthly,
                        coverage_fraction=coverage, country_order=COUNTRY_ORDER,
                        years=np.repeat(np.arange(1880, 2026), 12), months=np.tile(np.arange(1, 13), 146))
    np.savez_compressed(output.with_suffix(".weights.npz"), overlap_area_km2=weight_matrix,
                        country_order=COUNTRY_ORDER, latitude=lat, longitude=lon)
    report = {"year_range": [1880, 2025], "country_count": 191, "row_count": 146 * 191,
              "source": recorded_path(source), "source_sha256": snapshot_hash, "source_info": source_info,
              "annual_sha256": checksum(output),
              "geometry": recorded_path(geometry), "geometry_sha256": geometry_hash,
              "geometry_url": GEOMETRY_URL, "geometry_git_blob": GEOMETRY_BLOB,
              "geometry_release": "Natural Earth v5.1.2 repository tag, 1:10m Admin 0 Countries",
              "boundary_policy": "Fixed Natural Earth boundaries in every year; France includes territories in its feature, Norway excludes separately mapped Svalbard. Somaliland merged into Somalia; Northern Cyprus into Cyprus; Kosovo separate (XKX). Other dependencies are excluded from the board.",
              "method": "Fractional country/grid overlap area on a sphere (R=6371.0088 km); cylindrical equal-area coordinates with geographic edges densified to 0.1 degrees. Monthly area-weighted mean of available cells, then unweighted mean of all 12 country-months.",
              "minimum_monthly_coverage": minimum_coverage,
              "missing_policy": "Any positive available area qualifies by default; weights renormalized over available intersecting cells. No spatial or temporal gap filling. Annual N/A if any of 12 months is unusable. Partial coverage flagged and quantified.",
              "landmask_policy": "Country polygon intersection defines land area; the separate cell land-fraction mask is not multiplied again into polygon areas.",
              "limitations": "1200 km smoothed land-ocean reconstruction; tiny-country values share surrounding coarse cells. Coverage is spatial support, not a statistical uncertainty estimate. Historical comparison is diagnostic, not independent scientific certification.",
              "validation": {"baseline_1951_1980": True, "all_1752_months_present": True,
                             "annual_values_require_12_months": True, "unique_complete_country_year_grid": True,
                             "excluded_2026": True, "countries_with_geometry": 191},
              "missing_countries_by_year": {str(y): [c for ci, c in enumerate(COUNTRY_ORDER) if not np.isfinite(annual[y - 1880, ci])] for y in range(1880, 2026)},
              "spatial_support": spatial, "numpy_version": np.__version__, "shapely_version": shapely.__version__}
    if reference is not None:
        report["historical_comparison"] = validate_reference(annual, Path(reference))
    output.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Saved {output}: {146 * 191} country-years; 2025 N/A: {report['missing_countries_by_year']['2025']}", flush=True)
    return loaded, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gistemp", type=Path, default=SOURCE)
    parser.add_argument("--geometry", type=Path, default=GEOMETRY)
    parser.add_argument("--output", type=Path, default=RECOMPUTED)
    parser.add_argument("--minimum-coverage", type=float, default=0.0)
    parser.add_argument("--reference", type=Path, help="optional historical comparison CSV supplied separately")
    args = parser.parse_args()
    try:
        derive_dataset(args.gistemp, args.geometry, args.output, args.minimum_coverage, args.reference)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
