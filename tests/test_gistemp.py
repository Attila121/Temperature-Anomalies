import unittest

import numpy as np
from shapely import STRtree, box

from gistemp_data import (
    COUNTRY_ISO3, complete_annual, decode_anomalies, equal_area_geometry,
    monthly_country, overlap_weights,
)
from render_frame import COUNTRY_ORDER


class GistempTests(unittest.TestCase):
    def test_packed_fill_is_masked_and_kelvin_anomalies_are_not_absolute_temperatures(self):
        result = decode_anomalies(np.array([100, -125, 0, 32767], dtype=np.int16),
                                 {"units": "K", "_FillValue": [32767], "scale_factor": [0.01]})
        np.testing.assert_allclose(result[:3], [1, -1.25, 0])
        self.assertTrue(np.isnan(result[3]))

    def test_missing_cells_renormalize_weights_and_report_coverage(self):
        grid = np.array([[0, 4], [np.nan, 4], [np.nan, np.nan]])
        monthly, coverage = monthly_country(grid, np.array([0, 1]), np.array([3.0, 1.0]))
        np.testing.assert_allclose(monthly[:2], [1, 4])
        np.testing.assert_allclose(coverage, [1, 0.25, 0])
        self.assertTrue(np.isnan(monthly[2]))
        strict, _ = monthly_country(grid, np.array([0, 1]), np.array([3.0, 1.0]), 0.5)
        self.assertTrue(np.isnan(strict[1]))

    def test_annual_requires_every_month_and_uses_unweighted_monthly_mean(self):
        monthly = np.arange(24, dtype=float)
        monthly[20] = np.nan
        annual, missing = complete_annual(monthly)
        self.assertEqual(annual[0], 5.5)
        self.assertTrue(np.isnan(annual[1]))
        np.testing.assert_array_equal(missing, [0, 1])

    def test_small_country_without_cell_centres_still_has_overlap(self):
        small = box(0.05, 0.05, 0.1, 0.1)
        cells = np.array([equal_area_geometry(box(0, 0, 2, 2))], dtype=object)
        indices, areas = overlap_weights(small, cells, STRtree(cells))
        np.testing.assert_array_equal(indices, [0])
        self.assertGreater(areas[0], 0)
        self.assertAlmostEqual(areas[0], equal_area_geometry(small).area)

    def test_dateline_parts_are_not_wrapped_across_the_globe(self):
        from shapely.geometry import MultiPolygon
        country = MultiPolygon([box(179.5, 0, 180, 1), box(-180, 0, -179.5, 1)])
        cells = np.array([equal_area_geometry(box(-180, 0, -178, 2)),
                          equal_area_geometry(box(178, 0, 180, 2)),
                          equal_area_geometry(box(-1, 0, 1, 2))], dtype=object)
        indices, areas = overlap_weights(country, cells, STRtree(cells))
        np.testing.assert_array_equal(indices, [0, 1])
        self.assertAlmostEqual(areas[0], areas[1])

    def test_fixed_board_has_unique_explicit_country_codes(self):
        self.assertEqual(tuple(COUNTRY_ISO3), COUNTRY_ORDER)
        self.assertEqual(len(set(COUNTRY_ISO3.values())), 191)
        self.assertEqual(COUNTRY_ISO3["Hungary"], "HUN")
        self.assertEqual(COUNTRY_ISO3["Kosovo"], "XKX")
        self.assertEqual(COUNTRY_ISO3["South Sudan"], "SSD")


if __name__ == "__main__":
    unittest.main()
