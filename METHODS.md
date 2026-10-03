# Calculation and rendering methods

## Input and period

The exact bundled NASA GISTEMP v4 land-ocean snapshot uses GHCN v4, ERSST v5,
1200 km smoothing and a 2-degree grid. Its header records creation on
2026-09-08 and the 1951-1980 baseline. It contains January 1880 through August
2026. The calculation selects January 1880 through December 2025 and checks
all 1,752 monthly coordinates. Incomplete 2026 is excluded.

Packed fill values are masked before applying scale and offset. Kelvin
temperature differences equal Celsius differences; no 273.15 subtraction
is applied. Latitude/longitude centres and variable dimensions are checked
before aggregation.

## Country means

Use the fixed Natural Earth v5.1.2 repository-tag 1:10m Admin 0 Countries
geometries in every year. These are dataset boundaries, not reconstructions of
historical borders. Explicit ISO mappings match the 191-slot visualization.
The inherited board does not include every country: for example Belgium and
the United Kingdom have no slots.

Kosovo has a separate XKX slot. Somaliland is merged into Somalia and Northern
Cyprus into Cyprus. France includes overseas areas present in its feature;
Norway excludes separately mapped Svalbard. Other separately mapped dependencies
are excluded. See the derived report's `boundary_policy` and `spatial_support`.

For each country, intersect its geometry with every overlapping grid cell.
Areas use spherical cylindrical equal-area coordinates with Earth radius
6371.0088 km and polygon edges densified to 0.1 degrees. Weight each cell by
its intersecting area. Small countries receive values even without a grid
cell centre within their boundaries. The overlap areas must sum to the projected
country area within numerical tolerance.

For each month, renormalize the overlap weights over cells with available data.
The default requires any positive represented area and records its fraction of
the whole country area. `--minimum-coverage 0.8` instead requires 80% monthly
coverage. No missing grid cells or months are filled. The annual value is the
unweighted arithmetic mean of 12 usable country-month values; if any month is
unusable, the annual value is `N/A`.

Country polygons already define the intersection area. The separate coarse
land-fraction mask is not multiplied into the weights.

## Validation and limitations

Checks before export cover the baseline, grid, complete monthly coordinates,
country geometries, 12-month annual completeness, and unique full country/year
grid. The CSV is read back through the renderer's strict input validator.
Source and geometry hashes are included in every data row; the JSON report
also records the derived CSV hash and missing countries by year.

The gridded source is a 1200 km smoothed land-ocean reconstruction. Tiny countries
share surrounding coarse cells. Coverage measures spatial support, not
statistical uncertainty. Country-year values are project-derived estimates,
not an official NASA country dataset. Fixed contemporary boundaries affect
historical interpretation. The early years include missing values; all 191
slots have usable annual values in 2025 under the default coverage rule.

An optional `--reference PATH` produces diagnostic comparison with a historical
wide table. It is not needed for reproduction and has no numerical acceptance
tolerance. Source revisions and aggregation methods differ.

## Rendering

The fixed 16 x 12 board has 191 labels and one empty bottom-right slot.
Country names are inherited display labels, including historical spellings.
Bubble radius is `max(2.5, 39.2 * sqrt(abs(anomaly)))` pixels. Above the minimum
dot floor, area is proportional to magnitude. RGB colours interpolate between
five anchors and saturate at +/-2 C; radius and signed one-decimal value labels
use the full anomaly. All circles precede all labels to preserve label visibility.
Threefold supersampling supplies antialiasing.

The public release bundles DejaVu Sans regular and bold. It records the fonts
and configuration beside each rendered frame. Exact pixel reproduction across
different Pillow/FreeType builds is not guaranteed; use the recorded package
versions and font checksums for the closest match.

The video interpolates annual anomalies with `smoothstep(t) = t*t*(3-2*t)`.
Size and colour are recomputed from the interpolated anomaly, including sign
changes through zero. The large year shows the source year until the next
annual keyframe. Intermediate value labels are interpolated; the footer identifies
them as graphical transitions. A missing endpoint makes intermediate frames
`N/A`; original values are preserved at annual endpoints.
