"""Portable paths used by the standalone release and its metadata."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def recorded_path(path):
    """Record project-relative paths; external inputs retain only their filename."""
    path = Path(path).resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.name
