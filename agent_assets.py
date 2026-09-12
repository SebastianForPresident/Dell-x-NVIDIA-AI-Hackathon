"""Application-supplied case assets. Paths and measurements are never model inputs."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import hashlib

from forensics import load_boundary


@dataclass(frozen=True)
class CaseAssets:
    root: Path
    boundary: str | None = None
    weather: str | None = None
    crop: str | None = None
    before: str | None = None
    after: str | None = None
    before_date: str | None = None
    after_date: str | None = None
    selected_field: int = 0
    red_band: int = 1
    nir_band: int = 2
    weather_unit: str = "mm"

    def __post_init__(self):
        object.__setattr__(self, "root", Path(self.root).resolve(strict=True))
        if not self.root.is_dir():
            raise ValueError("Asset root must be a directory.")
        if type(self.selected_field) is not int or self.selected_field < 0:
            raise ValueError("selected_field must be a nonnegative integer.")
        if any(type(b) is not int or b < 1 for b in (self.red_band, self.nir_band)):
            raise ValueError("Band indices must be positive integers.")
        if self.red_band == self.nir_band:
            raise ValueError("Red and NIR bands must differ.")
        if self.weather_unit not in {"mm", "inches"}:
            raise ValueError("Weather unit must be mm or inches.")
        for value in (self.before_date, self.after_date):
            if value is not None:
                date.fromisoformat(value)
        for kind in ("boundary", "weather", "crop", "before", "after"):
            self.path(kind)

    def path(self, kind):
        relative = getattr(self, kind)
        if relative is None:
            return None
        path = (self.root / relative).resolve(strict=True)
        if not path.is_relative_to(self.root) or not path.is_file():
            raise ValueError("Asset must be a regular file inside the approved case directory.")
        return path

    def manifest(self):
        result = {key: getattr(self, key) for key in (
            "before_date", "after_date", "selected_field", "red_band", "nir_band", "weather_unit")}
        for kind in ("boundary", "weather", "crop", "before", "after"):
            path = self.path(kind)
            if path is None:
                result[kind] = None
            else:
                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                result[kind] = {"name": str(path.relative_to(self.root)), "sha256": digest}
        return result

    def fields(self):
        path = self.path("boundary")
        if path is None:
            return [], None
        fields = load_boundary(path.read_bytes())
        if self.selected_field >= len(fields):
            raise ValueError("Selected field is outside the supplied boundary collection.")
        return fields, fields[self.selected_field]["geometry"]
