# Bundled data

The input snapshot is bundled so reproduction does not depend on a changing
download. SHA-256 hashes and byte sizes are in `../release-manifest.json`;
run `python verify_release.py` from the project root to check them.

| File | Origin and role |
| --- | --- |
| `raw/gistemp1200_GHCNv4_ERSSTv5.nc.gz` | Original NASA GISTEMP v4 LOTI, 1200 km smoothed, 2-degree monthly grid |
| `raw/ne_10m_admin_0_countries.geojson` | Natural Earth v5.1.2 repository tag, 1:10m Admin 0 Countries |
| `derived/country-anomalies-gistemp-1880-2025.csv` | Project-derived country annual anomalies; 191 slots x 146 years = 27,886 rows |
| `derived/country-anomalies-gistemp-1880-2025.json` | Source metadata, checksums, method, boundary policy, validation and missing-country lists |

NASA header creation date: **2026-09-08**. Available source months: **1880-01
through 2026-08**. Selected full annual period: **1880-2025**. Baseline:
**1951-1980**. The original download date was not recorded; the source webpage
and citation guidance were checked on **2026-10-03** while preparing this folder.
The bundled file is authoritative for reproducing this release.

NASA source and current download guidance: [GISTEMP v4](https://data.giss.nasa.gov/gistemp/).
The current upstream file can change, including corrections to past months;
do not replace this snapshot when reproducing this release.

Boundary source: [pinned repository tag](https://github.com/nvkelso/natural-earth-vector/blob/v5.1.2/geojson/ne_10m_admin_0_countries.geojson).
Recorded Git blob: `5ebc66e25fc1af01edaebe9375c546655e04cf1e`.
Natural Earth data are in the public domain under its [terms of use](https://www.naturalearthdata.com/about/terms-of-use/).

## Annual CSV fields

| Field | Meaning |
| --- | --- |
| `country` | Exact country label used by the board |
| `iso3` | Explicit country code; Kosovo uses XKX |
| `continent` | Natural Earth continent label |
| `year` | Calendar year, 1880-2025 |
| `anomaly_c` | Annual anomaly in degrees Celsius relative to 1951-1980, or `N/A` |
| `coverage_fraction` | Mean monthly represented-area fraction |
| `minimum_monthly_coverage_fraction` | Lowest monthly represented-area fraction that year |
| `missing_months` | Count of unusable months; any positive count gives annual `N/A` |
| `n_grid_cells` | Number of intersecting grid cells with positive overlap |
| `effective_area_km2` | Sum of country/grid overlap areas |
| `quality_flag` | `complete`, `partial_spatial_coverage` or `missing_months` |
| `source` | Source dataset description |
| `dataset_version` | SHA-256 of the exact NASA snapshot |
| `geometry_version` | SHA-256 of the exact boundary file |

The renderer accepts a strict long CSV with `country,year,anomaly_c`; additional
metadata fields are allowed. Names must match `COUNTRY_ORDER` exactly. Quote
names containing commas. Empty, `NA`, `N/A` and `NaN` values are missing. Duplicate
country/year pairs, unknown labels, infinite values and years outside the period
are rejected. Missing values are never replaced with zero.

Monthly arrays and overlap weights can be recreated with `python gistemp_data.py`;
they are generated outputs rather than additional required inputs. See
[METHODS.md](../METHODS.md) for interpretation and limitations.
