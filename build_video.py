"""Encode country annual anomalies through 2025 as a smooth H.264 video."""

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

from reference_data import load_lipponen_csv
from project_paths import ROOT, recorded_path
from render_frame import COUNTRY_ORDER, RenderConfig, load_annual_csv, render_frame, resolve_font


def interpolate_values(start, end, fraction):
    """Tween only between two available annual values; never fill missing data."""
    if not math.isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError("fraction must be finite and between 0 and 1")
    if fraction == 0:
        return dict(start)
    if fraction == 1:
        return dict(end)
    return {country: None if start.get(country) is None or end.get(country) is None
            else (1 - fraction) * start[country] + fraction * end[country]
            for country in COUNTRY_ORDER}


def video_timeline(years, frames_per_year, hold_frames, transition):
    """Yield (source year, target year, interpolation weight, repetitions)."""
    if hold_frames:
        yield years[0], years[0], 0.0, hold_frames
    for start, end in zip(years, years[1:]):
        if transition == "none":
            yield start, start, 0.0, frames_per_year
            continue
        for frame in range(frames_per_year):
            fraction = frame / frames_per_year
            if transition == "smooth":
                fraction = fraction * fraction * (3 - 2 * fraction)
            yield start, end, fraction, 1
    yield years[-1], years[-1], 0.0, frames_per_year + hold_frames


def _render_job(job):
    year, values, config, footer, repetitions = job
    image = render_frame(year, values, config=config, source_lines=footer, year_label=str(year))
    return year, repetitions, image.tobytes()


def rendered_video_frames(jobs, workers):
    """Render in order with bounded buffering to avoid accumulating RGB frames."""
    if workers == 1:
        yield from map(_render_job, jobs)
        return
    jobs = iter(jobs)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        pending = deque()
        for _ in range(2 * workers):
            job = next(jobs, None)
            if job is None:
                break
            pending.append(pool.submit(_render_job, job))
        while pending:
            yield pending.popleft().result()
            job = next(jobs, None)
            if job is not None:
                pending.append(pool.submit(_render_job, job))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--lipponen-csv", type=Path, help="historical calibration preview")
    inputs.add_argument("--csv", type=Path, help="strict annual country CSV")
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--seconds-per-year", type=float, default=0.4)
    parser.add_argument("--hold-seconds", type=float, default=2)
    parser.add_argument("--supersampling", type=int, default=3)
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1), help="parallel frame renderers; 1 for serial rendering")
    parser.add_argument("--transitions", choices=("smooth", "linear", "none"), default="smooth",
                        help="smooth: ease in/out; linear: constant rate; none: annual steps")
    args = parser.parse_args()
    if not args.ffmpeg:
        parser.error("FFmpeg is required; supply --ffmpeg PATH")
    if args.workers < 1:
        parser.error("workers must be positive")
    if args.fps <= 0 or not math.isfinite(args.seconds_per_year) or args.seconds_per_year <= 0:
        parser.error("fps and seconds-per-year must be positive")
    if not math.isfinite(args.hold_seconds) or args.hold_seconds < 0:
        parser.error("hold-seconds must be finite and nonnegative")
    reference = None
    dataset_report = None
    if args.lipponen_csv:
        source = args.lipponen_csv
        data, reference = load_lipponen_csv(source)
        mode = "historical-reference-preview"
    elif args.csv:
        source = args.csv
        data = load_annual_csv(source)
        mode = "annual-country-dataset"
    else:
        from gistemp_data import ANNUAL, GEOMETRY, RECOMPUTED, SOURCE, checksum, derive_dataset
        source = ANNUAL
        metadata = source.with_suffix(".json")
        if source.is_file() and metadata.is_file():
            dataset_report = json.loads(metadata.read_text(encoding="utf-8"))
        if (dataset_report is None or dataset_report.get("source_sha256") != checksum(SOURCE)
                or dataset_report.get("geometry_sha256") != checksum(GEOMETRY)
                or dataset_report.get("annual_sha256") != checksum(source)
                or dataset_report.get("minimum_monthly_coverage") != 0.0):
            source = RECOMPUTED
            data, dataset_report = derive_dataset(output=source)
        else:
            data = load_annual_csv(source)
        mode = "gistemp-country-annual"
    years = sorted(data)
    if not years or years != list(range(years[0], years[-1] + 1)):
        parser.error("annual dataset must contain contiguous years")
    frames_per_year = max(1, round(args.seconds_per_year * args.fps))
    if args.transitions != "none" and frames_per_year < 2:
        parser.error("smooth transitions require at least two frames per year")
    hold_frames = round(args.hold_seconds * args.fps)
    if args.output is None:
        suffix = "" if args.transitions == "none" else f"-{args.transitions}"
        name = "reference" if args.lipponen_csv else "gistemp" if mode == "gistemp-country-annual" else "annual"
        args.output = ROOT / f"output/temperature-anomalies-{name}-{years[0]}-{years[-1]}{suffix}.mp4"
    cfg = RenderConfig(supersampling=args.supersampling, title_end_year=years[-1],
                       credit_line=f"{'Historical preview' if args.lipponen_csv else 'Annual country anomalies'} {years[0]}–{years[-1]}")
    footer = (
        f"Historical preview: Antti Lipponen, supplied Tdata.csv ({years[0]}–{years[-1]})." if args.lipponen_csv
        else "NASA GISTEMP v4 LOTI, ERSSTv5, 1200 km smoothing; fixed country boundaries." if mode == "gistemp-country-annual"
        else f"Annual country dataset: {source.name}",
        "Graphical transitions between annual values; intermediate labels are interpolated." if args.transitions != "none"
        else "Annual data only; each frame displays one annual observation.",
        "GISTEMP base period 1951–1980. Missing country-year values: N/A.",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    partial = args.output.with_name(args.output.stem + ".partial.mp4")
    log_path = args.output.with_suffix(".ffmpeg.log")
    command = [str(args.ffmpeg), "-hide_banner", "-loglevel", "warning", "-y",
               "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "1920x1080",
               "-framerate", str(args.fps), "-i", "pipe:0",
               "-an", "-c:v", "libx264", "-preset", "medium",
               "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(partial)]
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
        try:
            frame_count = 0
            previous_year = None
            jobs = ((year, interpolate_values(data[year], data[target], fraction), cfg, footer, repetitions)
                    for year, target, fraction, repetitions in video_timeline(years, frames_per_year, hold_frames, args.transitions))
            for year, repetitions, encoded in rendered_video_frames(jobs, args.workers):
                for _ in range(repetitions):
                    process.stdin.write(encoded)
                frame_count += repetitions
                if year != previous_year and ((year - years[0]) % 5 == 0 or year == years[-1]):
                    print(f"Rendering {year} ({year - years[0] + 1}/{len(years)} years, {frame_count} frames)", flush=True)
                previous_year = year
            process.stdin.close()
            if process.wait() != 0:
                raise RuntimeError(f"FFmpeg failed; see {log_path}")
        except BaseException:
            process.kill()
            process.wait()
            raise
    partial.replace(args.output)
    with source.open("rb") as handle:
        input_hash = hashlib.file_digest(handle, "sha256").hexdigest()
    manifest = {
        "mode": mode, "year_range": [years[0], years[-1]],
        "source": recorded_path(source), "source_sha256": input_hash, "reference_mapping": reference,
        "dataset_report": dataset_report,
        "config": asdict(cfg), "fonts": {r: recorded_path(resolve_font(r, getattr(cfg, f"{r}_font"))) for r in ("title", "label", "footer")},
        "fps": args.fps, "frames_per_year": frames_per_year, "total_frames": frame_count,
        "render_workers": args.workers,
        "duration_seconds": frame_count / args.fps, "size": [1920, 1080],
        "transitions": args.transitions,
        "interpolation": "smoothstep(t)=t*t*(3-2*t) applied to annual anomalies" if args.transitions == "smooth"
        else "linear interpolation of annual anomalies" if args.transitions == "linear" else "none",
        "year_labels": "source year throughout each transition; switches at the next annual keyframe",
        "value_labels": "interpolated during transitions; actual annual values at keyframes",
        "missing_transition_policy": "N/A unless both endpoints exist; exact annual values preserved at endpoints",
        "intermediate_frames_are_observations": False,
        "ffmpeg_command": [recorded_path(command[0]), *command[1:-1], recorded_path(partial)],
        "missing_countries_by_year": {y: [c for c in COUNTRY_ORDER if data[y].get(c) is None] for y in years},
        "scientific_validation": "source/month/baseline/geometry/annual-completeness checks and historical diagnostic comparison" if dataset_report
        else "historical calibration source" if args.lipponen_csv else "provenance and scientific validation are supplied by the CSV producer",
    }
    args.output.with_suffix(".json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {args.output.resolve()} ({manifest['duration_seconds']:.1f}s, {frame_count} frames)", flush=True)


if __name__ == "__main__":
    main()
