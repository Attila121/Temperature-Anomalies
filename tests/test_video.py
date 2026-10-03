import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from build_video import interpolate_values, main, video_timeline


class TransitionTests(unittest.TestCase):
    def test_zero_crossing_uses_value_interpolation(self):
        result = interpolate_values({"Hungary": -2}, {"Hungary": 2}, 0.5)
        self.assertEqual(result["Hungary"], 0)
        self.assertEqual(interpolate_values({"Hungary": -2}, {"Hungary": 2}, 0.25)["Hungary"], -1)

    def test_missing_endpoints_are_not_zero_filled(self):
        start = {"Hungary": 1, "USA": None}
        end = {"Hungary": None, "USA": 2}
        self.assertEqual(interpolate_values(start, end, 0), start)
        self.assertEqual(interpolate_values(start, end, 1), end)
        middle = interpolate_values(start, end, 0.5)
        self.assertIsNone(middle["Hungary"])
        self.assertIsNone(middle["USA"])

    def test_smooth_timeline_preserves_duration_endpoints_and_easing(self):
        frames = list(video_timeline(list(range(1880, 2020)), 12, 60, "smooth"))
        self.assertEqual(sum(item[3] for item in frames), 1800)
        self.assertEqual(frames[0], (1880, 1880, 0, 60))
        self.assertEqual(frames[-1], (2019, 2019, 0, 72))
        interval = [item for item in frames if item[0] == 1880 and item[1] == 1881]
        self.assertEqual(len(interval), 12)
        self.assertEqual(interval[0][2], 0)
        self.assertAlmostEqual(interval[6][2], 0.5)
        self.assertLess(interval[1][2], 1 / 12)
        self.assertEqual(sorted(item[2] for item in interval), [item[2] for item in interval])

    def test_step_and_linear_modes_share_duration(self):
        for mode in ("smooth", "linear", "none"):
            self.assertEqual(sum(item[3] for item in video_timeline([1890, 1891], 12, 60, mode)), 144)
        linear = list(video_timeline([1890, 1891], 12, 0, "linear"))
        self.assertAlmostEqual(linear[3][2], 0.25)

    def test_invalid_weights_fail(self):
        for fraction in (-0.1, 1.1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                interpolate_values({}, {}, fraction)

    def test_2025_timeline_preserves_full_range_and_duration(self):
        frames = list(video_timeline(list(range(1880, 2026)), 12, 60, "smooth"))
        self.assertEqual(frames[-1], (2025, 2025, 0, 72))
        self.assertEqual(sum(item[3] for item in frames), 1872)

    def test_encoded_frames_keep_source_year_until_next_annual_keyframe(self):
        class Encoder:
            def __init__(self, command, **kwargs):
                self.stdin = io.BytesIO()
                Path(command[-1]).write_bytes(b"test-video")

            def wait(self):
                return 0

        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder) / "annual.csv", Path(folder) / "video.mp4"
            source.write_text("country,year,anomaly_c\nHungary,2012,1\nHungary,2013,2\nHungary,2014,3\n", encoding="utf-8")
            argv = ["build_video.py", "--csv", str(source), "--output", str(output),
                    "--ffmpeg", "test-ffmpeg", "--fps", "2", "--seconds-per-year", "1", "--hold-seconds", "0", "--workers", "1"]
            with patch("sys.argv", argv), patch("build_video.subprocess.Popen", Encoder), \
                    patch("build_video.render_frame", return_value=Image.new("RGB", (1, 1))) as render:
                main()
            self.assertEqual([call.kwargs["year_label"] for call in render.call_args_list],
                             ["2012", "2012", "2013", "2013", "2014"])
            report = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(report["total_frames"], 6)
            self.assertEqual(report["year_range"], [2012, 2014])


if __name__ == "__main__":
    unittest.main()
