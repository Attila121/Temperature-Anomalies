"""Compare explicitly registered screenshot/render regions, without guessing crops."""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageEnhance
from project_paths import recorded_path


def compare_frames(reference, rendered, output_dir, *, reference_box=None, rendered_box=None):
    with Image.open(reference) as source:
        ref = source.convert("RGB")
    with Image.open(rendered) as source:
        frame = source.convert("RGB")
    for img, box in ((ref, reference_box), (frame, rendered_box)):
        if box is not None:
            left, top, right, bottom = box
            if not (0 <= left < right <= img.width and 0 <= top < bottom <= img.height):
                raise ValueError("comparison crop must lie inside its image")
    if reference_box is not None:
        ref = ref.crop(reference_box)
    if rendered_box is not None:
        frame = frame.crop(rendered_box)
    if ref.size != frame.size:
        if reference_box is None or rendered_box is None:
            raise ValueError("sizes differ: provide both crop boxes for explicit registration")
        frame = frame.resize(ref.size, Image.Resampling.LANCZOS)
    error = np.asarray(ref, dtype=np.float32) - np.asarray(frame, dtype=np.float32)
    metrics = {
        "reference": recorded_path(reference), "rendered": recorded_path(rendered),
        "reference_box": reference_box, "rendered_box": rendered_box,
        "comparison_size": ref.size, "mae_rgb_0_255": float(np.mean(np.abs(error))),
        "rmse_rgb_0_255": float(np.sqrt(np.mean(error ** 2))),
        "changed_pixel_fraction": float(np.mean(np.any(error != 0, axis=2))),
        "interpretation": "Diagnostic only. Cropping, resampling, source revisions, missing countries and intentional style changes affect these metrics.",
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    Image.blend(ref, frame, 0.5).save(output_dir / "overlay.png")
    ImageEnhance.Brightness(ImageChops.difference(ref, frame)).enhance(4).save(output_dir / "difference-x4.png")
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("rendered", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reference-box", type=int, nargs=4, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    parser.add_argument("--rendered-box", type=int, nargs=4, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"))
    args = parser.parse_args()
    try:
        print(json.dumps(compare_frames(args.reference, args.rendered, args.output_dir,
                                       reference_box=args.reference_box, rendered_box=args.rendered_box), indent=2))
    except (ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
