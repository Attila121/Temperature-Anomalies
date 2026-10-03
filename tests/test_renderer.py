import csv
import math
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from compare_frames import compare_frames
from reference_data import load_lipponen_csv
from render_frame import (
    COUNTRY_ORDER, COUNTRY_ROWS, RenderConfig, anomaly_color,
    bubble_radius, format_anomaly, grid_xy, load_annual_csv, render_frame,
)


class EncodingTests(unittest.TestCase):
    def test_layout_preserves_comma_names_and_empty_slot(self):
        self.assertEqual([len(row.split("|")) for row in COUNTRY_ROWS], [16] * 11 + [15])
        self.assertEqual(len(set(COUNTRY_ORDER)), 191)
        self.assertEqual(COUNTRY_ORDER[11], "Bahamas, The")
        self.assertEqual(COUNTRY_ORDER[37], "Congo, DR")
        self.assertEqual(COUNTRY_ORDER[-1], "Zimbabwe")
        self.assertEqual(grid_xy(0), (97.8, 185.9))
        self.assertAlmostEqual(grid_xy(191)[0], 1813.8)
        self.assertAlmostEqual(grid_xy(191)[1], 940.5)

    def test_area_is_proportional_outside_minimum_dot(self):
        self.assertEqual(bubble_radius(0), 2.5)
        self.assertAlmostEqual(bubble_radius(-1), 39.2)
        self.assertAlmostEqual(bubble_radius(2) ** 2 / bubble_radius(1) ** 2, 2)
        self.assertAlmostEqual(bubble_radius(-4), 78.4)

    def test_anchor_interpolation_and_saturation(self):
        self.assertEqual(anomaly_color(-2), (69, 117, 183))
        self.assertEqual(anomaly_color(0), (247, 249, 199))
        self.assertEqual(anomaly_color(2), (225, 66, 41))
        self.assertEqual(anomaly_color(-1.5), (118, 164, 208))
        self.assertEqual(anomaly_color(8), anomaly_color(2))
        self.assertGreater(bubble_radius(8), bubble_radius(2))

    def test_missing_and_signed_display(self):
        self.assertEqual(format_anomaly(None), "N/A")
        self.assertEqual(format_anomaly(math.nan), "N/A")
        self.assertEqual(format_anomaly(-0.01), "+0.0°C")
        self.assertEqual(format_anomaly(3.12), "+3.1°C")
        for fn in (bubble_radius, anomaly_color):
            for value in (math.nan, math.inf):
                with self.assertRaises(ValueError):
                    fn(value)


class InputTests(unittest.TestCase):
    def csv_file(self, rows, directory):
        path = Path(directory) / "annual.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["country", "year", "anomaly_c"])
            writer.writerows(rows)
        return path

    def test_long_csv_and_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.csv_file([["Bahamas, The", 2025, 2.15], ["Hungary", 2025, ""]], folder)
            values = load_annual_csv(path)[2025]
            self.assertEqual(values["Bahamas, The"], 2.15)
            self.assertIsNone(values["Hungary"])

    def test_csv_rejects_duplicate_unknown_infinite_and_out_of_scope(self):
        cases = [
            [["Hungary", 2025, 1], ["Hungary", 2025, 2]],
            [["Hungray", 2025, 1]], [["Hungary", 2025, "inf"]], [["Hungary", 2026, 1]],
        ]
        with tempfile.TemporaryDirectory() as folder:
            for rows in cases:
                with self.subTest(rows=rows), self.assertRaises(ValueError):
                    load_annual_csv(self.csv_file(rows, folder))

    def test_optional_reference_adapter_maps_aliases_and_missing_values(self):
        # Synthetic fixture: no private historical data is needed by this suite.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "reference.csv"
            path.write_text("Country,ISOA3,Continent,1890,1891\n"
                            "Bahamas,BHS,North America,1.25,N/A\n"
                            "Belgium,BEL,Europe,0.5,0.6\n", encoding="utf-8")
            data, report = load_lipponen_csv(path)
        self.assertEqual(report["mapped_countries"], 1)
        self.assertEqual(report["excluded_source_countries"], ["Belgium"])
        self.assertEqual(report["aliases_applied"], {"Bahamas": "Bahamas, The"})
        self.assertEqual(data[1890]["Bahamas, The"], 1.25)
        self.assertIsNone(data[1891]["Bahamas, The"])


class ImageTests(unittest.TestCase):
    def test_real_raster_has_expected_encodings_and_no_empty_slot_label(self):
        image = render_frame(2025, {"Afghanistan": -2, "Albania": 4},
                             config=RenderConfig(supersampling=1))
        self.assertEqual(image.size, (1920, 1080))
        self.assertEqual(image.mode, "RGB")
        self.assertEqual(image.getpixel((98, 220)), anomaly_color(-2))
        self.assertEqual(image.getpixel((212, 240)), anomaly_color(4))
        self.assertEqual(image.getpixel((1814, 941)), (247, 247, 247))
        # Missing Algeria has no zero-anomaly bubble.
        self.assertEqual(image.getpixel((327, 220)), (247, 247, 247))

    def test_renderer_rejects_bad_years_names_and_infinity(self):
        for year, values in ((2026, {}), (1890.0, {}), (1890, {"Hungray": 1}),
                             (1890, {"Hungary": math.inf})):
            with self.subTest(year=year, values=values), self.assertRaises(ValueError):
                render_frame(year, values)

    def test_comparison_metrics_and_registration_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            a, b = root / "a.png", root / "b.png"
            Image.new("RGB", (10, 10), (100, 100, 100)).save(a)
            Image.new("RGB", (10, 10), (110, 110, 110)).save(b)
            metrics = compare_frames(a, b, root / "comparison")
            self.assertEqual(metrics["mae_rgb_0_255"], 10)
            self.assertEqual(metrics["rmse_rgb_0_255"], 10)
            self.assertEqual(metrics["changed_pixel_fraction"], 1)
            Image.new("RGB", (11, 10)).save(b)
            with self.assertRaises(ValueError):
                compare_frames(a, b, root / "comparison")


if __name__ == "__main__":
    unittest.main()
