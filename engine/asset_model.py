from dataclasses import dataclass, field, asdict
from typing import Optional
import json
import os

@dataclass
class Asset:
    id: str
    name: str
    lat: float
    lon: float
    asset_type: str                  # e.g. "residential_masonry", "commercial_steel"
    replacement_value: float
    construction_material: str       # wood_frame | masonry | steel | concrete | mixed
    year_built: int
    stories: int
    basement: bool
    roof_type: str                   # flat | gable | hip
    elevation_m: float               # above local base flood elevation
    floor_area_m2: float
    region: str                      # iso3 country code

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Asset":
        return cls(
            id=str(d["id"]),
            name=str(d["name"]),
            lat=float(d["lat"]),
            lon=float(d["lon"]),
            asset_type=str(d["asset_type"]),
            replacement_value=float(d["replacement_value"]),
            construction_material=str(d.get("construction_material", "masonry")),
            year_built=int(d.get("year_built", 2000)),
            stories=int(d.get("stories", 1)),
            basement=bool(d.get("basement", False)),
            roof_type=str(d.get("roof_type", "gable")),
            elevation_m=float(d.get("elevation_m", 0.0)),
            floor_area_m2=float(d.get("floor_area_m2", 200.0)),
            region=str(d.get("region", "GBR")),
        )


def load_asset_types() -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "data", "asset_types.json")
    with open(os.path.normpath(path)) as f:
        return json.load(f)


def get_default_asset_params(asset_type: str) -> dict:
    catalog = load_asset_types()
    return catalog.get(asset_type, catalog.get("residential_masonry", {}))
