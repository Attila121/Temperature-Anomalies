# Sources and third-party notices

## NASA GISTEMP

The input gridded data come from NASA's Goddard Institute for Space Studies.
Credit **NASA GISS/GISTEMP** when using the source data. Country aggregates
and rendered frames in this project are calculated from that source; they
are not official NASA country products.

NASA asks users to cite the dataset webpage and its latest scholarly publication:

- GISTEMP Team, 2026: GISS Surface Temperature Analysis (GISTEMP), version 4.
  NASA Goddard Institute for Space Studies. [Dataset webpage](https://data.giss.nasa.gov/gistemp/),
  citation guidance accessed 2026-10-03. The original snapshot download date is
  unknown; its NetCDF header records creation on 2026-09-08.
- Lenssen, N., G. A. Schmidt, M. Hendrickson, P. Jacobs, M. Menne and R. Ruedy,
  2024: A GISTEMPv4 observational uncertainty ensemble. Journal of Geophysical
  Research: Atmospheres, 129, e2023JD040179.
  [doi:10.1029/2023JD040179](https://doi.org/10.1029/2023JD040179).

The snapshot and boundary checksums are recorded in the release manifest and
the derived data report. No project code license is assigned to third-party data.

## Natural Earth

Made with Natural Earth. The bundled Admin 0 Countries geometry is from the
[v5.1.2 repository tag](https://github.com/nvkelso/natural-earth-vector/blob/v5.1.2/geojson/ne_10m_admin_0_countries.geojson).
Natural Earth states that its raster and vector map data are public domain:
[terms of use](https://www.naturalearthdata.com/about/terms-of-use/).

## DejaVu fonts

Unmodified `DejaVuSans.ttf` and `DejaVuSans-Bold.ttf` are redistributed with
the complete [font license](assets/fonts/LICENSE_DEJAVU). Bitstream and Arev
copyright and permission notices are retained. DejaVu changes are public domain.
The local copies were obtained from the fonts bundled with Matplotlib 3.10.8;
their SHA-256 hashes are in the release manifest. Matplotlib is not a runtime
dependency of this project.

## Visual reference

The fixed country-board arrangement follows the Antti Lipponen visualization
used as the project's reference:
[Temperature Anomalies by Country 1880-2017](https://www.flickr.com/photos/150411108@N06/43350961005/).
That Flickr page links to [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/),
checked 2026-10-03. Attribution is retained in rendered frames. Changes include
recalculation through 2025, numerical value labels, missing-value handling and
portable typography. This license notice concerns the visual reference, not
a newly selected license for the project's code.

The original supplied script and table retain
their original notices in the private experiment archive. They, along with
reference screenshots and source video, are excluded from this public folder.
The public calculation does not require the historical table.

## Project code

A license for this project's code has not yet been selected. This document
records third-party attribution and does not grant a new license over the code.
