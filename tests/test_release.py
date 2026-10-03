"""Integration checks for a public copy with no experimental inputs."""

import csv
import json
import unittest
from pathlib import Path

from gistemp_data import ANNUAL, GEOMETRY, SOURCE, checksum
from project_paths import ROOT
from render_frame import COUNTRY_ORDER, load_annual_csv, resolve_font
from verify_release import verify_release


class ReleaseTests(unittest.TestCase):
    def test_bundled_file_inventory_is_intact(self):
        errors, count = verify_release()
        self.assertGreater(count, 0)
        self.assertEqual(errors, [])

    def test_bundled_dataset_has_the_complete_country_year_grid_and_provenance(self):
        report = json.loads(ANNUAL.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertEqual(report["annual_sha256"], checksum(ANNUAL))
        self.assertEqual(report["source_sha256"], checksum(SOURCE))
        self.assertEqual(report["geometry_sha256"], checksum(GEOMETRY))
        data = load_annual_csv(ANNUAL)
        self.assertEqual(sorted(data), list(range(1880, 2026)))
        self.assertTrue(all(set(values) == set(COUNTRY_ORDER) for values in data.values()))
        self.assertTrue(all(value is not None for value in data[2025].values()))
        self.assertTrue(any(value is None for value in data[1880].values()))
        with ANNUAL.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 27886)
        self.assertEqual({row["dataset_version"] for row in rows}, {report["source_sha256"]})
        self.assertEqual({row["geometry_version"] for row in rows}, {report["geometry_sha256"]})

    def test_default_fonts_are_inside_the_release(self):
        for role in ("title", "label", "footer"):
            self.assertTrue(Path(resolve_font(role)).is_relative_to(ROOT / "assets/fonts"))


if __name__ == "__main__":
    unittest.main()
